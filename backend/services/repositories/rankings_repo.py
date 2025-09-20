# backend/services/repositories/rankings_repo.py
from __future__ import annotations
from typing import Optional, Sequence
from sqlmodel import select
from sqlalchemy.orm import selectinload

from backend.models.dbmodels import TrackRanking, Track

def get_rankings_for_decade_genre(db, decade_id: int, genre_id: int) -> Sequence[TrackRanking]:
    q = (
        select(TrackRanking)
        .where(TrackRanking.decade_id == decade_id, TrackRanking.genre_id == genre_id)
        .options(selectinload(TrackRanking.track))  # preload Track
        .order_by(TrackRanking.ranking.asc())
    )
    return db.exec(q).all()

def get_single_ranking_with_track(db, ranking_id: int) -> Optional[TrackRanking]:
    q = (
        select(TrackRanking)
        .where(TrackRanking.id == ranking_id)
        .options(selectinload(TrackRanking.track))
        .limit(1)
    )
    return db.exec(q).first()
