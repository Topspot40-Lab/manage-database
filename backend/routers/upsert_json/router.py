from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlmodel import Session

from backend.database import get_db
from .service import (
    upsert_json_and_reset_service,
    upsert_collection_json_service,   # ✅ add this
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["JSON & Files"])


@router.post("/collections/upsert-json-and-reset/{slug}")
async def upsert_collection_json_and_reset(
    slug: str = Path(..., description="Collection slug, e.g., power_ballads"),  # ✅ optional Path meta
    replace_rankings: bool = Query(True),
    reset_intro_mp3s: bool = Query(True),
    preserve_intro_text: bool = Query(False),
    preserve_detail: bool = Query(True),
    preserve_artist_description: bool = Query(True),
    tracklist_id: int = Query(1),
    dry_run: bool = Query(False),
    store_json_copy: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Upsert a collection JSON (data/json_files/collections/{slug}.json) as a virtual (decade='collections', genre='<name>')."""
    try:
        return await upsert_collection_json_service(
            db=db,
            slug=slug,
            replace_rankings=replace_rankings,
            reset_intro_mp3s=reset_intro_mp3s,
            preserve_intro_text=preserve_intro_text,
            preserve_detail=preserve_detail,
            preserve_artist_description=preserve_artist_description,
            tracklist_id=tracklist_id,
            dry_run=dry_run,
            store_json_copy=store_json_copy,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in collections/upsert-json-and-reset")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upsert-json-and-reset/{decade}/{genre}")
async def upsert_json_and_reset(
    decade: str = Path(..., description="e.g., 1980s"),
    genre: str = Path(..., description="e.g., rock"),
    replace_rankings: bool = Query(True, description="Delete all existing rankings for this combo then insert from JSON"),
    reset_intro_mp3s: bool = Query(True, description="Delete intro MP3s in storage for this combo before changes"),
    preserve_intro_text: bool = Query(False, description="Keep existing TrackRanking.intro when present"),
    preserve_detail: bool = Query(True),
    preserve_artist_description: bool = Query(True),
    tracklist_id: int = Query(1),
    dry_run: bool = Query(False),
    store_json_copy: bool = Query(False, description="Upload JSON blob to Storage for auditing (optional)"),
    db: Session = Depends(get_db),
):
    """Upsert a decade/genre JSON from data/json_files/{decade}/{decade}_{genre}_en.json."""
    try:
        return await upsert_json_and_reset_service(
            db=db,
            decade=decade,
            genre=genre,
            replace_rankings=replace_rankings,
            reset_intro_mp3s=reset_intro_mp3s,
            preserve_intro_text=preserve_intro_text,
            preserve_detail=preserve_detail,
            preserve_artist_description=preserve_artist_description,
            tracklist_id=tracklist_id,
            dry_run=dry_run,
            store_json_copy=store_json_copy,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in upsert-json-and-reset")
        raise HTTPException(status_code=500, detail=str(e))
