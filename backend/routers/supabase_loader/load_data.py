# backend/routers/supabase_loader/load_data.py
from fastapi import APIRouter, Query, Depends, Path, HTTPException
from typing import Literal
from sqlmodel import Session, select
from backend.database import get_db
from backend.services.supabase_loader_service import load_decade_genre, load_collection
from backend.state import current_decade_genre, current_collection
from backend.models.collection_models import Collection

router = APIRouter(tags=["Supabase: Load Data & Context"])

# ─────────────────────────────────────────────
# Load Decade + Genre
# ─────────────────────────────────────────────
@router.get("/load-decade-genre-data")
def load_decade_genre_data(
    decade: str = Query(..., description="Decade name, e.g. '1980s'"),
    genre: str = Query(..., description="Genre name, e.g. 'country'"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    db: Session = Depends(get_db),
):
    """Load ranked track data for a decade/genre combination."""
    result = load_decade_genre(db, decade, genre, tts_language)
    current_decade_genre.update({"decade": decade, "genre": genre, "lang": result["language"]})
    return result

# ─────────────────────────────────────────────
# Load Collection by Slug (underscores allowed)
# ─────────────────────────────────────────────
@router.get("/load-collection-data/{slug}")
def load_collection_data(
    slug: str = Path(..., description="Collection slug, e.g. 'motown_magic'", pattern=r"^[a-z0-9_]+$"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    db: Session = Depends(get_db),
):
    """Load ranked track data for a named collection using its slug."""
    # Optional safety: ensure collection exists
    coll = db.exec(select(Collection).where(Collection.slug == slug)).first()
    if not coll:
        raise HTTPException(status_code=404, detail=f"Collection not found for slug '{slug}'")

    result = load_collection(db, slug, tts_language)
    current_collection.update({"collection": slug, "lang": result["language"]})
    return result

# ─────────────────────────────────────────────
# Get Current Context
# ─────────────────────────────────────────────
@router.get("/current-context")
def get_current_context():
    """Return whichever mode (decade-genre or collection) is currently loaded."""
    mode = "collection" if current_collection.get("collection") else (
        "decade_genre" if current_decade_genre.get("decade") and current_decade_genre.get("genre") else None
    )
    return {
        "mode": mode,
        "decade_genre": current_decade_genre,
        "collection": current_collection,
    }
