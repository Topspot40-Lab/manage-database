# backend/services/track_resolver.py
from __future__ import annotations
from typing import Optional
from sqlmodel import Session, select, col
from backend.models.dbmodels import Track  # your existing Track model

def resolve_track_id_by_meta(db: Session, title: str, artist_name: str, year: int | None = None) -> Optional[int]:
    # strict match first (case-insensitive)
    stmt = select(Track.id).where(
        col(Track.title).ilike(title) & col(Track.artist_name).ilike(artist_name)
    )
    if year:
        stmt = stmt.where(Track.release_year == year)

    found = db.exec(stmt).first()
    if found:
        return found

    # Optionally loosen matching here (e.g., strip "Original Motion Picture Cast", etc.)
    return None
