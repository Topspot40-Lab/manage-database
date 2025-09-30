# backend/utils/upsert.py
from sqlmodel import select
from backend.models.dbmodels import Track

def upsert_track_by_spotify_id(db, payload) -> int:
    """
    Natural key = spotify_track_id.
    Updates the existing Track if SID exists; else inserts a new Track.
    Returns the canonical track_id to use for FKs.
    """
    sid = payload["spotify_track_id"]
    existing = db.exec(select(Track).where(Track.spotify_track_id == sid)).first()
    if existing:
        # Update allowed fields; NEVER move SIDs across rows.
        for k in ("track_name","artist_id","album_name","duration_ms","popularity","album_artwork","detail"):
            if k in payload and payload[k] is not None:
                setattr(existing, k, payload[k])
        db.add(existing)
        db.flush()
        return existing.id

    obj = Track(**payload)  # includes spotify_track_id
    db.add(obj)
    db.flush()
    return obj.id
