from __future__ import annotations

import logging
import sqlalchemy
from fastapi import HTTPException
from sqlmodel import Session

from pathlib import Path
import json

from backend.utils.json_helpers import load_full_json_file
from .parsers import normalize_root_payload
from .upserters import (
    SchemaError,          # ✅ import here
    ensure_combo,
    upsert_artists,
    upsert_tracks,
    upsert_rankings,
)

from .storage_ops import maybe_reset_intro_mp3s

logger = logging.getLogger(__name__)

async def upsert_json_and_reset_service(
    *,
    db: Session,
    decade: str,
    genre: str,
    replace_rankings: bool,
    reset_intro_mp3s: bool,
    preserve_intro_text: bool,
    preserve_detail: bool,
    preserve_artist_description: bool,
    tracklist_id: int,
    dry_run: bool,
    store_json_copy: bool,
):
    # (Optional) log DB schema if available
    try:
        if db.bind is not None:
            logger.info("Schema: %s", sqlalchemy.inspect(db.bind).default_schema_name)
    except Exception:
        pass

    filename = f"{decade}_{genre}_en.json"

    # 1) Load JSON
    try:
        data = load_full_json_file(decade, filename)
        logger.info("Loaded JSON: %s", filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"JSON file not found: {filename}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read error: {e}")

    # 2) Normalize incoming payload into consistent structure
    payload = normalize_root_payload(data, fallback_decade=decade, fallback_genre=genre)

    if dry_run:
        return {
            "status": "dry_run",
            "decade": payload.decade_name,
            "genre": payload.genre_name,
            "would_upsert": {
                "artists": len(payload.artists),
                "tracks": len(payload.tracks),
                "rankings": len(payload.rankings),
            },
            "would_reset_intro_mp3s": bool(reset_intro_mp3s),
            "replace_rankings": bool(replace_rankings),
            "tracklist_id": tracklist_id,
            "note": "No DB writes or storage changes performed.",
        }

    # 3–7) Single transaction for DB work
    try:
        logger.info(
            "Upsert start — artists=%d tracks=%d rankings=%d (decade=%s, genre=%s, tracklist_id=%d, replace_rankings=%s)",
            len(payload.artists), len(payload.tracks), len(payload.rankings),
            payload.decade_name, payload.genre_name, tracklist_id, replace_rankings,
        )

        with db.begin():
            decade_obj, genre_obj, decade_genre = ensure_combo(db, payload.decade_name, payload.genre_name)

            artist_map = upsert_artists(
                db=db,
                artists_in=payload.artists,
                genre_obj=genre_obj,
                preserve_artist_description=preserve_artist_description,
            )

            upsert_tracks(
                db=db,
                tracks_in=payload.tracks,
                artist_map=artist_map,
                preserve_detail=preserve_detail,
            )

            ranking_result = upsert_rankings(
                db=db,
                rankings_in=payload.rankings,
                decade_genre=decade_genre,
                tracklist_id=tracklist_id,
                replace_rankings=replace_rankings,
                preserve_intro_text=preserve_intro_text,
                artist_map=artist_map,
                genre_obj=genre_obj,  # for fallback artist linking
            )

            logger.info(
                "Rankings processed: upserted=%d, skipped=%d, deduped=%d",
                ranking_result.upserted, ranking_result.skipped, ranking_result.dupes
            )

    except SchemaError as e:  # <-- add this (import from .upserters)
        # Raised when TrackRanking schema doesn't expose 'rank' or 'ranking'
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upsert failed")
        raise HTTPException(status_code=500, detail=f"Upsert failed: {e}")

    # 8) Storage cleanup (non-fatal)
    maybe_reset_intro_mp3s(
        reset=reset_intro_mp3s,
        decade_name=payload.decade_name,
        genre_name=payload.genre_name,
        languages=("en",),
    )

    # 9) Optional: audit JSON upload (left as TODO)
    if store_json_copy:
        logger.info("JSON storage upload requested; implement helper when ready.")

    return {
        "status": "success",
        "decade": payload.decade_name,
        "genre": payload.genre_name,
        "replace_rankings": replace_rankings,
        "reset_intro_mp3s": reset_intro_mp3s,
        "tracklist_id": tracklist_id,
        "note": "Upsert completed; intro MP3s cleared if requested. Proceed to regenerate TTS.",
    }


# Add this in the same module as upsert_json_and_reset_service



async def upsert_collection_json_service(
    *,
    db: Session,
    slug: str,
    replace_rankings: bool,
    reset_intro_mp3s: bool,
    preserve_intro_text: bool,
    preserve_detail: bool,
    preserve_artist_description: bool,
    tracklist_id: int,
    dry_run: bool,
    store_json_copy: bool,
):
    # Optional: log DB schema
    try:
        if db.bind is not None:
            logger.info("Schema: %s", sqlalchemy.inspect(db.bind).default_schema_name)
    except Exception:
        pass

    # 1) Load collection JSON
    path = Path("data/json_files/collections") / f"{slug}.json"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded collection JSON: %s", path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Collection JSON not found: {path.name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Read error: {e}")

    # 2) Normalize into the same structure your upserters expect
    collection_meta = data.get("collection") or {}
    decade_name = "collections"  # virtual bucket
    genre_name = (collection_meta.get("name") or slug).strip() or slug

    artists  = data.get("artist") or []
    tracks   = data.get("track") or []
    rankings = data.get("track_ranking") or []

    if isinstance(artists, dict):  artists = [artists]
    if isinstance(tracks, dict):   tracks = [tracks]
    if isinstance(rankings, dict): rankings = [rankings]

    if dry_run:
        return {
            "status": "dry_run",
            "collection": genre_name,
            "slug": slug,
            "would_upsert": {
                "artists": len(artists),
                "tracks": len(tracks),
                "rankings": len(rankings),
            },
            "would_reset_intro_mp3s": bool(reset_intro_mp3s),
            "replace_rankings": bool(replace_rankings),
            "tracklist_id": tracklist_id,
            "note": "No DB writes or storage changes performed.",
        }

    # 3) Transaction: reuse the same upsert building blocks
    try:
        with db.begin():
            decade_obj, genre_obj, decade_genre = ensure_combo(db, decade_name, genre_name)

            artist_map = upsert_artists(
                db=db,
                artists_in=artists,
                genre_obj=genre_obj,
                preserve_artist_description=preserve_artist_description,
            )

            upsert_tracks(
                db=db,
                tracks_in=tracks,
                artist_map=artist_map,
                preserve_detail=preserve_detail,
            )

            ranking_result = upsert_rankings(
                db=db,
                rankings_in=rankings,
                decade_genre=decade_genre,
                tracklist_id=tracklist_id,
                replace_rankings=replace_rankings,
                preserve_intro_text=preserve_intro_text,
                artist_map=artist_map,
                genre_obj=genre_obj,
            )

            logger.info(
                "Collection rankings: upserted=%d, skipped=%d, deduped=%d",
                ranking_result.upserted, ranking_result.skipped, ranking_result.dupes
            )
    except SchemaError as e:
        # Thrown if TrackRanking has neither 'rank' nor 'ranking'
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Collection upsert failed")
        raise HTTPException(status_code=500, detail=f"Upsert failed: {e}")

    # 4) Optional storage reset (treat as the virtual combo)
    maybe_reset_intro_mp3s(
        reset=reset_intro_mp3s,
        decade_name=decade_name,
        genre_name=genre_name,
        languages=("en",),
    )

    if store_json_copy:
        logger.info("JSON storage upload requested; implement helper when ready.")

    return {
        "status": "success",
        "collection": genre_name,
        "slug": slug,
        "virtual_decade": decade_name,
        "replace_rankings": replace_rankings,
        "reset_intro_mp3s": reset_intro_mp3s,
        "tracklist_id": tracklist_id,
        "note": "Upsert completed (as a virtual (collections, <name>) combo).",
    }
