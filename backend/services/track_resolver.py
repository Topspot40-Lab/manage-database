# backend/services/track_resolver.py
from typing import Optional
from sqlalchemy import select, func, or_
from sqlmodel import Session
from backend.models.dbmodels import Track, Artist

def resolve_track_id_by_meta(
    db: Session,
    track_name: Optional[str],
    artist_name: Optional[str],
    year: Optional[int] = None,
) -> Optional[int]:
    if not track_name:
        return None

    t = track_name.strip()
    a = (artist_name or "").strip()

    # Exact, case-insensitive on title; join to Artist for name match
    stmt = (
        select(Track.id)
        .select_from(Track)
        .join(Artist, Track.artist_id == Artist.id, isouter=True)
        .where(func.lower(Track.track_name) == t.lower())
    )
    if year is not None and hasattr(Track, "year_released"):
        stmt = stmt.where(Track.year_released == year)
    if a:
        name_conds = [func.lower(Artist.artist_name) == a.lower()]
        if hasattr(Track, "artist_display_name"):
            name_conds.append(func.lower(Track.artist_display_name) == a.lower())
        stmt = stmt.where(or_(*name_conds))

    found = db.exec(stmt).scalar_one_or_none()
    if found:
        return found

    # Fuzzy fallback
    stmt = (
        select(Track.id)
        .select_from(Track)
        .join(Artist, Track.artist_id == Artist.id, isouter=True)
        .where(Track.track_name.ilike(f"%{t}%"))
    )
    if year is not None and hasattr(Track, "year_released"):
        stmt = stmt.where(Track.year_released.between(year - 2, year + 2))
    if a:
        like_conds = [Artist.artist_name.ilike(f"%{a}%")]
        if hasattr(Track, "artist_display_name"):
            like_conds.append(Track.artist_display_name.ilike(f"%{a}%"))
        stmt = stmt.where(or_(*like_conds))

    return db.exec(stmt.limit(1)).scalar_one_or_none()


def get_or_create_artist_id(db: Session, artist_name: str) -> Optional[int]:
    if not artist_name:
        return None
    a = artist_name.strip()
    aid = db.exec(
        select(Artist.id).where(func.lower(Artist.artist_name) == a.lower())
    ).scalar_one_or_none()
    if aid:
        return aid
    artist = Artist(artist_name=a)
    db.add(artist)
    db.flush()   # assign PK without committing
    return artist.id


def get_or_create_track_id(
    db: Session,
    track_name: str,
    artist_id: int,
    year: Optional[int] = None,
    spotify_track_id: Optional[str] = None,
) -> Optional[int]:
    if not track_name or not artist_id:
        return None

    t = track_name.strip()

    stmt = select(Track.id).where(
        func.lower(Track.track_name) == t.lower(),
        Track.artist_id == artist_id,
    )
    if year is not None and hasattr(Track, "year_released"):
        stmt = stmt.where(Track.year_released == year)

    tid = db.exec(stmt).scalar_one_or_none()
    if tid:
        return tid

    track = Track(track_name=t, artist_id=artist_id)
    if year is not None and hasattr(Track, "year_released"):
        track.year_released = year
    if spotify_track_id and hasattr(Track, "spotify_track_id"):
        track.spotify_track_id = spotify_track_id

    db.add(track)
    db.flush()  # assign PK
    return track.id


def ensure_track_for_meta(
    db: Session,
    track_name: Optional[str],
    artist_name: Optional[str],
    year: Optional[int] = None,
    spotify_track_id: Optional[str] = None,
) -> Optional[int]:
    """Create missing Artist/Track as needed, return Track.id."""
    if not track_name or not artist_name:
        return None
    aid = get_or_create_artist_id(db, artist_name)
    if not aid:
        return None
    return get_or_create_track_id(db, track_name, aid, year, spotify_track_id)
