from __future__ import annotations

import json
from typing import Literal
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import Session, select
import logging

from backend.database import get_db
from backend.utils.naming import normalize_language_code_canon
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track, Artist
from backend.services.narration_texts import assemble_narration_texts

# server-side playback helpers
from backend.services.radio_runtime import (
    narration_keys_for,
    maybe_play_bed, play_narrations, play_track_with_skip,
    log_collection_header_and_texts,
)

# bucket resolver for language-aware audio buckets
from backend.services.playback_helpers import bucket_for

from backend.config.volume import PLAY_FULL_TRACK
from backend.services.narration_bundle import urls_for_rank_collection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/supabase/collections", tags=["Collections"])


# Helper
def _titleize(s: str | None) -> str:
    return s.replace("_", " ").title() if s else ""


def collection_intro_jobs(*, lang: str, slug: str, rank: int):
    bucket = bucket_for(lang, "intro")
    key = f"collections-intro/{slug}_{rank:02d}.mp3"
    return [(bucket, key, "collection", slug, rank)]


# ─────────────────────────────────────────────────────────────
# PLAY SINGLE TRACK BY RANK
# ─────────────────────────────────────────────────────────────
@router.get("/play-track-by-rank")
async def play_track_by_rank(
    collection_slug: str = Query(...),
    rank: int = Query(...),
    play_intro: bool | str = Query(True),
    play_detail: bool | str = Query(True),
    play_track: bool | str = Query(True),
    play_artist_description: bool | str = Query(True),
    tts_language: Literal["en","es","ptbr","pt-BR"] = Query("en"),
    db: Session = Depends(get_db),
):
    def str_to_bool(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        return str(val).strip().lower() in {"true", "1", "yes", "y", "t"}

    play_intro = str_to_bool(play_intro)
    play_detail = str_to_bool(play_detail)
    play_artist_description = str_to_bool(play_artist_description)
    play_track = str_to_bool(play_track)

    lang = normalize_language_code_canon(tts_language)
    coll = db.exec(select(Collection).where(Collection.slug == collection_slug)).first()
    if not coll:
        return {"error": f"No Collection for {collection_slug!r}"}

    ctr_row = db.exec(
        select(
            CollectionTrackRanking.id,
            CollectionTrackRanking.ranking,
            CollectionTrackRanking.track_id,
            CollectionTrackRanking.intro,
        ).where(
            CollectionTrackRanking.collection_id == coll.id,
            CollectionTrackRanking.ranking == rank
        )
    ).first()
    if not ctr_row:
        return {"error": f"No ranking #{rank} in collection {collection_slug}"}

    ctr = getattr(ctr_row, "_mapping", ctr_row)
    track = db.get(Track, ctr["track_id"])
    artist = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return {"error": "Track or Artist not found"}

    intro_text = ctr.get("intro")
    detail_text = (
        getattr(track, "detail_text", None)
        or getattr(track, "track_detail", None)
        or getattr(track, "detail", None)
    )

    log_collection_header_and_texts(
        lang=lang,
        collection=coll,
        ctr=ctr,
        track=track,
        artist=artist,
        intro=intro_text,
        detail_text=detail_text,
    )

    detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
        lang=lang, track=track, artist=artist
    )

    intro_jobs = (
        collection_intro_jobs(lang=lang, slug=coll.slug, rank=rank)
        if play_intro else []
    )

    if intro_jobs or (play_detail and detail_bucket and detail_key) or (
        play_artist_description and artist_bucket and artist_key
    ):
        await maybe_play_bed()

    await play_narrations(
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist=play_artist_description,
        intro_jobs=intro_jobs,
        detail_bucket=detail_bucket,
        detail_key=detail_key,
        artist_bucket=artist_bucket,
        artist_key=artist_key,
    )

    if play_track and track.spotify_track_id:
        skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
        if skipped_mid:
            return {
                "status": "skipped",
                "collection": collection_slug,
                "rank": rank,
            }

    texts = assemble_narration_texts(
        track=track,
        artist=artist,
        collection_intro=ctr.get("intro"),
        mode="collection"
    )

    return {"status": "success", "collection": collection_slug, "rank": rank, **texts}


# ─────────────────────────────────────────────────────────────
# PLAY COLLECTION SEQUENCE (count up / down / random)
# ─────────────────────────────────────────────────────────────
@router.get("/play-sequence", response_class=HTMLResponse)
async def play_sequence(
    request: Request,
    collection_slug: str = Query(..., description="'All' plays all collections combined"),
    start_rank: int = Query(1, ge=1, le=40),
    end_rank: int = Query(40, ge=1, le=40),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    ui: int = Query(1, description="1=HTML player (browser). 0=JSON bundle."),
    server: bool = Query(True, description="True=server-side playback like Car Mode."),
    expires: int = Query(300, ge=60, le=3600),
    db: Session = Depends(get_db),
):
    lang = normalize_language_code_canon(tts_language)

    # Handle "All" collections
    if collection_slug.lower() == "all":
        collections = db.exec(select(Collection)).all()
        if not collections:
            return JSONResponse({"error": "No collections found."}, status_code=404)
    else:
        coll = db.exec(select(Collection).where(Collection.slug == collection_slug)).first()
        if not coll:
            return JSONResponse({"error": f"No Collection for {collection_slug!r}"}, status_code=404)
        collections = [coll]

    # Gather all ranking rows
    rows = []
    for c in collections:
        rows.extend(
            db.exec(
                select(CollectionTrackRanking)
                .where(CollectionTrackRanking.collection_id == c.id)
                .order_by(CollectionTrackRanking.ranking)
            ).all()
        )
    if not rows:
        return JSONResponse({"error": "No rankings found for selection."}, status_code=404)

    # Filter by rank range
    rows = [r for r in rows if start_rank <= r.ranking <= end_rank]
    if not rows:
        return JSONResponse({"error": f"No tracks in rank range {start_rank}-{end_rank}."}, status_code=404)

    # Determine play order
    order = sorted({r.ranking for r in rows})
    if mode == "count_up":
        play_order = sorted(order)
    elif mode == "count_down":
        play_order = sorted(order, reverse=True)
    else:
        import random
        play_order = list(order)
        random.shuffle(play_order)

    # Server-side playback (Car Mode)
    if server:
        results = []
        for rk in play_order:
            for r in [x for x in rows if x.ranking == rk]:
                track = db.get(Track, r.track_id)
                artist = db.get(Artist, track.artist_id) if track else None
                if not track or not artist:
                    continue

                coll_for_row = next((c for c in collections if c.id == r.collection_id), None)
                log_collection_header_and_texts(
                    lang=lang,
                    collection=coll_for_row,
                    ctr=r,
                    track=track,
                    artist=artist,
                    intro=getattr(r, "intro", None),
                    detail_text=getattr(track, "detail_text", None),
                )

                await maybe_play_bed()
                await play_narrations(
                    play_intro=False,
                    play_detail=False,
                    play_artist=False,
                    intro_jobs=collection_intro_jobs(lang=lang, slug=coll_for_row.slug, rank=rk),
                    detail_bucket=None, detail_key=None,
                    artist_bucket=None, artist_key=None,
                )

                results.append({
                    "rank": rk,
                    "track": track.track_name,
                    "artist": artist.artist_name if artist else None,
                    "album_name": getattr(track, "album_name", None),
                    "album_artwork": getattr(track, "album_artwork", None),
                    "collection": coll_for_row.slug if coll_for_row else None,
                })

        return JSONResponse({
            "status": "loaded",
            "collections": [c.slug for c in collections],
            "mode": mode,
            "range": [start_rank, end_rank],
            "language": lang,
            "tracks_loaded": results,
        })

    # Browser mode
    sequence = []
    for r in rows:
        coll_for_row = next((c for c in collections if c.id == r.collection_id), None)
        if not coll_for_row:
            continue
        t = db.get(Track, r.track_id)
        a = db.get(Artist, t.artist_id) if t else None
        if not t:
            continue

        bundle, err = urls_for_rank_collection(
            db=db,
            lang=lang,
            collection_id=coll_for_row.id,
            rank=r.ranking,
            use_intro=play_intro,
            use_detail=play_detail,
            use_artist=play_artist_description,
            expires=expires,
            request=request,
            collection_slug=coll_for_row.slug,
        )
        if err or not bundle:
            continue

        sequence.append({
            "rank": r.ranking,
            "collection": coll_for_row.slug,
            "track_name": getattr(t, "track_name", None),
            "artist_name": getattr(a, "artist_name", None) if a else None,
            "album_name": getattr(t, "album_name", None),
            "album_artwork": getattr(t, "album_artwork", None),
            **bundle,
        })

    if mode == "count_up":
        sequence.sort(key=lambda s: s["rank"])
    elif mode == "count_down":
        sequence.sort(key=lambda s: s["rank"], reverse=True)
    else:
        import random
        random.shuffle(sequence)

    return JSONResponse({
        "collections": [c.slug for c in collections],
        "mode": mode,
        "language": lang,
        "range": [start_rank, end_rank],
        "play_track": play_track,
        "expires": expires,
        "sequence": sequence
    })
