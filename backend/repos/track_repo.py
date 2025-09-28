from sqlmodel import Session
from backend.models.dbmodels import Track, Artist

def get_track_and_artist(db: Session, track_id: int) -> tuple[Track|None, Artist|None]:
    track = db.get(Track, track_id)
    artist = db.get(Artist, track.artist_id) if track else None
    return track, artist
