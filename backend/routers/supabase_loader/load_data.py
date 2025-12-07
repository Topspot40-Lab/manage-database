# backend/routers/supabase_loader/load_data.py

from fastapi import APIRouter, Query, Depends, Path, HTTPException
from typing import Literal
from sqlmodel import Session, select

from backend.database import get_db
from backend.models.collection_models import Collection
from backend.services.supabase_loader_service import load_collection
from backend.routers.decade_genre_player import get_sequence_decade_genre
from backend.state import current_decade_genre, current_collection

router = APIRouter(tags=["Supabase"])

# ─────────────────────────────────────────────
# 🔥 FAST LOAD — USE get_sequence_decade_genre()
# ─────────────────────────────────────────────
@router.get("/load-decade-genre-data")
async def load_decade_genre_data(
    decade: str = Query(..., description="Decade name, e.g. '1980s'"),
    genre: str = Query(..., description="Genre name, e.g. 'country'"),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    db: Session = Depends(get_db),
):
    """
    Load ranked track metadata FAST using the /decade-genre/get-sequence logic.
    No narration files. No slow loaders.
    """

    # ✅ FIX: get_sequence_decade_genre is async — MUST await
    result = await get_sequence_decade_genre(
        decade=decade,
        genre=genre,
        start_rank=start_rank,
        end_rank=end_rank,
        db=db,
    )

    current_decade_genre.update({
        "decade": decade,
        "genre": genre,
        "lang": result.get("language", "en"),
    })

    return result


# ─────────────────────────────────────────────
# Load Collection by Slug (ASYNC FIX APPLIED)
# ─────────────────────────────────────────────
@router.get("/load-collection-data/{slug}")
async def load_collection_data(
    slug: str = Path(..., description="Collection slug, e.g. 'motown_magic'", pattern=r"^[a-z0-9_]+$"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    db: Session = Depends(get_db),
):
    """Load ranked track metadata for a named collection (FAST)."""

    coll = db.exec(select(Collection).where(Collection.slug == slug)).first()
    if not coll:
        raise HTTPException(404, f"Collection not found for slug '{slug}'")

    # ⭐ FIX: load_collection is async → MUST await
    result = await load_collection(db, slug, tts_language)

    current_collection.update({
        "collection": slug,
        "lang": result.get("language", "en"),
    })

    return result


# ─────────────────────────────────────────────
# Current Context
# ─────────────────────────────────────────────
@router.get("/current-context")
def get_current_context():
    mode = "collection" if current_collection.get("collection") else (
        "decade_genre" if current_decade_genre.get("decade") else None
    )
    return {
        "mode": mode,
        "decade_genre": current_decade_genre,
        "collection": current_collection,
    }
