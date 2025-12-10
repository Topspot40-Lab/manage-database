# backend/routers/collection_player.py
from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from fastapi import APIRouter, Query
from sqlmodel import select
from fastapi.responses import JSONResponse

from backend.database import get_db_session
from backend.models.dbmodels import (
    Track,
    Artist,
    Collection,
    CollectionTrackRanking,
)

from backend.routers.playback_control import (
    start_new_sequence,
    cancel_current_sequence,
    _flags,
)

from backend.services.spotify.playback import play_spotify_track

from backend.services.radio_runtime import (
    log_header_and_texts,
    collection_intro_jobs,
    narration_keys_for,
    play_narrations,
    _update_flags,
    _respect_user_controls,
    play_track_with_skip,
    _ensure_volume_ok,
)

from backend.config.volume import PLAY_FULL_TRACK

router = APIRouter(prefix="/supabase/collections", tags=["Supabase: Collections"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERNAL BACKGROUND TASK — COLLECTION PLAYBACK
# ─────────────────────────────────────────────
async def _run_play_sequence_collection(
    *,
    collection_slug: str,
    start_rank: int,
    end_rank: int,
    mode: Literal["count_up", "count_down", "random"],
    tts_language: str,
    play_intro: bool,
    play_detail: bool,
    play_artist_description: bool,
    play_track: bool,
    text_intro: bool,
    text_detail: bool,
    text_artist_description: bool,
    voice_style: Literal["before", "over"] = "before",
):
    logger.info(
        f"🎧 COLLECTION START: {collection_slug} "
        f"{start_rank}-{end_rank} mode={mode} voice_style={voice_style}"
    )

    # Fetch rows
    with get_db_session() as db:
        q = (
            select(
                Track,
                Artist,
                CollectionTrackRanking.ranking,
            )
            .join(Artist, Artist.id == Track.artist_id)
            .join(CollectionTrackRanking, CollectionTrackRanking.track_id == Track.id)
            .join(Collection, Collection.id == CollectionTrackRanking.collection_id)
            .where(
                Collection.slug == collection_slug,
                CollectionTrackRanking.ranking >= start_rank,
                CollectionTrackRanking.ranking <= end_rank,
            )
            .order_by(CollectionTrackRanking.ranking)  # ✅ THIS IS THE SPEED KEY
        )

        rows = db.exec(q).all()

    if not rows:
        logger.warning(f"⚠️ No tracks found for collection: {collection_slug}")
        await cancel_current_sequence()
        return

    # Sorting
    if mode == "count_down":
        rows.reverse()
    elif mode == "random":
        random.shuffle(rows)
    # count_up already correct from SQL order

    _flags.mode = "collection"
    _flags.context = {"collection_slug": collection_slug}
    _flags.cancel_requested = False
    _flags.is_playing = True
    _flags.stopped = False

    # ─────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────
    for track, artist, rank in rows:

        if _flags.cancel_requested:
            logger.info("⏭️ Skip/Next detected — aborting collection sequence.")
            break

        logger.info("──────────────────────────────────────────────")
        logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

        _update_flags(
            phase="prelude",
            lang=tts_language,
            mode="collection",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )

        await _respect_user_controls()

        log_header_and_texts(
            lang=tts_language,
            track=track,
            artist=artist,
            tr_rows=[],
        )

        intro_jobs = (
            collection_intro_jobs(
                lang=tts_language,
                collection_slug=collection_slug,
                rank=rank
            )
            if play_intro else []
        )

        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
            lang=tts_language,
            track=track,
            artist=artist,
        )

        # ─────────────────────────────────────────────
        # OVER MODE
        # ─────────────────────────────────────────────
        if voice_style == "over" and play_track and track.spotify_track_id:

            # ✅ Non-blocking volume safety
            asyncio.create_task(_ensure_volume_ok())

            # ✅ Start track immediately
            play_spotify_track(track.spotify_track_id)

            # ✅ Narration runs in background
            asyncio.create_task(
                play_narrations(
                    play_intro=play_intro,
                    play_detail=play_detail,
                    play_artist=play_artist_description,
                    intro_jobs=intro_jobs,
                    detail_bucket=detail_bucket,
                    detail_key=detail_key,
                    artist_bucket=artist_bucket,
                    artist_key=artist_key,
                    lang=tts_language,
                    mode="collection",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    voice_style="over",
                )
            )

            await play_track_with_skip(
                track=track,
                lang=tts_language,
                mode="collection",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
                full_flag=PLAY_FULL_TRACK,
                already_playing=True,
            )

        # ─────────────────────────────────────────────
        # BEFORE MODE
        # ─────────────────────────────────────────────
        else:
            # ✅ CORRECT SEQUENTIAL FLOW (no background tasks)
            await play_narrations(
                play_intro=play_intro,
                play_detail=play_detail,
                play_artist=play_artist_description,
                intro_jobs=intro_jobs,
                detail_bucket=detail_bucket,
                detail_key=detail_key,
                artist_bucket=artist_bucket,
                artist_key=artist_key,
                lang=tts_language,
                mode="collection",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
                voice_style="before",
            )

            if play_track:
                await play_track_with_skip(
                    track=track,
                    lang=tts_language,
                    mode="collection",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    full_flag=PLAY_FULL_TRACK,
                )

        await _respect_user_controls()
        await asyncio.sleep(0.5)

    logger.info("✅ Collection playback finished cleanly.")
    await cancel_current_sequence()


# ─────────────────────────────────────────────
# PUBLIC — START PLAYBACK
# ─────────────────────────────────────────────
@router.get("/play-collection-sequence")
async def play_collection_sequence(
    collection_slug: str = Query(...),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_artist_description: bool = Query(True),
    play_track: bool = Query(True),
    text_intro: bool = Query(True),
    text_detail: bool = Query(False),
    text_artist_description: bool = Query(False),
    voice_style: Literal["before", "over"] = Query("before"),
):
    logger.info(
        "▶ COLLECTION REQUEST: slug=%s %s-%s mode=%s lang=%s "
        "play_intro=%s play_detail=%s play_artist=%s play_track=%s voice_style=%s",
        collection_slug,
        start_rank,
        end_rank,
        mode,
        tts_language,
        play_intro,
        play_detail,
        play_artist_description,
        play_track,
        voice_style,
    )

    try:
        coro = _run_play_sequence_collection(
            collection_slug=collection_slug,
            start_rank=start_rank,
            end_rank=end_rank,
            mode=mode,
            tts_language=tts_language,
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist_description=play_artist_description,
            play_track=play_track,
            text_intro=text_intro,
            text_detail=text_detail,
            text_artist_description=text_artist_description,
            voice_style=voice_style,
        )

        await start_new_sequence(coro)

    except Exception as exc:
        logger.exception("❌ Failed to start collection sequence: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "collection_start_failed",
                "detail": str(exc),
            },
        )

    return {
        "status": "started",
        "collection": collection_slug,
        "mode": mode,
        "range": [start_rank, end_rank],
        "voice_style": voice_style,
    }
