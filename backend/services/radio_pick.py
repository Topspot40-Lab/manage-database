# backend/services/radio_pick.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Tuple
from sqlmodel import Session
from backend.models.dbmodels import Track, Artist, TrackRanking
from backend.services.db_queries import get_random_track, get_rankings_for_track, get_artist_by_id

TRow = Tuple[TrackRanking, str, str]  # (TrackRanking, decade_name, genre_name)


@dataclass
class TrackPick:
    track: Track
    artist: Artist
    rankings: List[TRow]


def fetch_random_pick(db: Session) -> Optional[TrackPick]:
    """Fetch a random playable track + its artist + all ranking rows for header rendering."""
    track = get_random_track(db)
    if not track:
        return None
    artist = get_artist_by_id(db, track.artist_id)
    if not artist:
        return None
    tr_rows = get_rankings_for_track(db, track.id) or []
    return TrackPick(track=track, artist=artist, rankings=tr_rows)
