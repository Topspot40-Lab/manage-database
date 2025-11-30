# backend/routers/collection_player.py
from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from fastapi import APIRouter, Query, Depends
from sqlmodel import select

from backend.database import get_db_session, get_db
from backend.models.dbmodels import (
    Track,
    Artist,
    Collection,
    CollectionTrackRanking,
)

# Playback controller
from backend.routers.playback_control import (
    start_new_sequence,
    cancel_current_sequence,
    _flags,
)

# Narration + runtime
from backend.services.radio_runtime import (
    log_header_and_texts,
    collection_intro_jobs,
    narration_keys_for,
    play_narrations,
    _update_flags,
    _respect_user_controls,
    play_track_with_skip,
)

from backend.config.volume import PLAY_FULL_TRACK


router = APIRouter(prefix="/supabase", tags=["Supabase: Collections"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERNAL BACKGROUND TASK (FULL COLLECTION RUN)
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
):
    logger.info(
        f"🎧 COLLECTION START: {collection_slug} {start_rank}-{end_rank} mode={mode}"
    )

    # Load rows
    with get_db_session() as db:
        q = (
            select(Track, Artist, CollectionTrackRanking, Collection)
            .join(Artist, Artist.id == Track.artist_id)
            .join(CollectionTrackRanking, CollectionTrackRanking.track_id == Track.id)
            .join(Collection, Collection.id == CollectionTrackRanking.collection_id)
            .where(
                Collection.slug == collection_slug,
                CollectionTrackRanking.ranking >= start_rank,
                CollectionTrackRanking.ranking <= end_rank,
            )
        )

        rows = db.exec(q).all()

    if not rows:
        logger.warning(f"⚠️ No tracks found for collection: {collection_slug}")
        await cancel_current_sequence()
        return

    # Sorting mode
    if mode == "count_up":
        rows.sort(key=lambda r: r[2].ranking)
    elif mode == "count_down":
        rows.sort(key=lambda r: r[2].ranking, reverse=True)
    else:
        random.shuffle(rows)

    _flags.mode = "collection"
    _flags.context = {"collection_slug": collection_slug}

    # ─────────────────────────────────────────────
    # MAIN PLAYBACK LOOP
    # ─────────────────────────────────────────────
    for track, artist, ctr_rank, coll in rows:
        rank = ctr_rank.ranking

        if _flags.cancel_requested:
            logger.info("🛑 Cancel requested — stopping collection playback.")
            break

        logger.info("──────────────────────────────────────────────")
        logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

        # UI flag updates
        _update_flags(
            phase="prelude",
            lang=tts_language,
            mode="collection",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )
        await _respect_user_controls()

        # ─────────────────────────────────────────────
        # ⭐ SINGLE-PLAY SHORTCUT
        # ─────────────────────────────────────────────
        is_single_play = (start_rank == end_rank)

        if is_single_play:
            logger.info("🎯 Single-play shortcut engaged")

            from backend.services.playback_orchestrator import play_one_server_side

            await play_one_server_side(
                lang=tts_language,
                track=track,
                artist=artist,
                play_intro=play_intro,
                play_detail=play_detail,
                play_artist_description=play_artist_description,
                play_track=play_track,
            )

            await _respect_user_controls()
            continue

        # ─────────────────────────────────────────────
        # NARRATION PHASE
        # ─────────────────────────────────────────────
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
                rank=rank,
            )
            if play_intro
            else []
        )

        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
            lang=tts_language,
            track=track,
            artist=artist,
        )

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
        )

        # ─────────────────────────────────────────────
        # SPOTIFY TRACK PLAYBACK
        # ─────────────────────────────────────────────
        if play_track:
            await play_track_with_skip(
                track=track,
                lang=tts_language,
                mode="collection",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
                full_flag=PLAY_FULL_TRACK,   # 🔥 now consistent
            )

        await _respect_user_controls()
        await asyncio.sleep(0.5)

    await cancel_current_sequence()
    logger.info("✅ Collection playback finished cleanly.")
