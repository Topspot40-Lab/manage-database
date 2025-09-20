# backend/services/repositories/tracks_repo.py
from __future__ import annotations
from typing import Optional
from sqlmodel import select
from backend.models.dbmodels import Track

def get_track_by_id(db, track_id: int) -> Optional[Track]:
    return db.exec(select(Track).where(Track.id == track_id).limit(1)).first()
