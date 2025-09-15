from __future__ import annotations

import logging
import sqlalchemy
from fastapi import HTTPException
from sqlmodel import Session

from backend.utils.json_helpers import load_full_json_file
from .parsers import normalize_root_payload
from .upserters import (
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
