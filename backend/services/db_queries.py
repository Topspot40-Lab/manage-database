# backend/services/db_queries.py
from sqlmodel import Session, select
from typing import Optional, List, Tuple
from backend.models import Track, TrackRanking, DecadeGenre, Decade, Genre, Artist
from sqlalchemy import func

def get_decade_genre(db: Session, decade: str, genre: str) -> Optional[DecadeGenre]:
    stmt = (
        select(DecadeGenre)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .where(Decade.decade_name == decade)
        .where(Genre.genre_name == genre)
    )
    return db.exec(stmt).first()

def get_rankings_for_combo(db: Session, decade_genre_id: int) -> List[TrackRanking]:
    return db.exec(
        select(TrackRanking).where(TrackRanking.decade_genre_id == decade_genre_id)
    ).all()

def get_random_track(db: Session) -> Optional[Track]:
    # Prefer tracks with spotify ids so playback works
    stmt = select(Track).where(Track.spotify_track_id.isnot(None)).order_by(func.random()).limit(1)
    return db.exec(stmt).first()

def get_rankings_for_track(db: Session, track_id: int) -> List[Tuple[TrackRanking, str, str]]:
    """
    Returns [(TrackRanking, decade_name, genre_name), ...] for the given track.
    """
    stmt = (
        select(TrackRanking, Decade.decade_name, Genre.genre_name)
        .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .where(TrackRanking.track_id == track_id)
        .order_by(Decade.decade_name, Genre.genre_name, TrackRanking.ranking)
    )
    return db.exec(stmt).all()

def get_artist_by_id(db: Session, artist_id: int) -> Optional[Artist]:
    return db.get(Artist, artist_id)
