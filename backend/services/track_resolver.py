from typing import Optional
from sqlalchemy import select, func, or_, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session
from backend.models.dbmodels import Track, Artist


# ---- small helpers ---------------------------------------------------------

def _as_int_id(val) -> Optional[int]:
    """Coerce SELECT results (int/tuple/Row) into an int id or None."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if hasattr(val, "_mapping"):
        try:
            return int(next(iter(val._mapping.values())))
        except Exception:
            return None
    if isinstance(val, (tuple, list)) and val:
        try:
            return int(val[0])
        except Exception:
            return None
    return None


def _set_local_timeouts(db: Session):
    """Relax aggressive timeouts only for the current transaction."""
    try:
        db.exec(text("SET LOCAL statement_timeout = '30s'"))
        db.exec(text("SET LOCAL lock_timeout = '5s'"))
    except Exception:
        # Not fatal on SQLite / older PG / restricted roles.
        pass


# ---- resolvers/creators ----------------------------------------------------

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

    row = db.exec(stmt).first()
    tid = _as_int_id(row)
    if tid:
        return tid

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

    row = db.exec(stmt.limit(1)).first()
    return _as_int_id(row)


def get_or_create_artist_id(db: Session, artist_name: str) -> Optional[int]:
    if not artist_name:
        return None
    a = artist_name.strip()

    row = db.exec(
        select(Artist.id).where(func.lower(Artist.artist_name) == a.lower())
    ).first()
    aid = _as_int_id(row)
    if aid:
        return aid

    artist = Artist(artist_name=a)
    db.add(artist)
    try:
        db.flush()  # assign PK
        return artist.id
    except IntegrityError:
        # Another txn inserted it first; reselect
        db.rollback()
        row = db.exec(
            select(Artist.id).where(func.lower(Artist.artist_name) == a.lower())
        ).first()
        return _as_int_id(row)


def get_or_create_track_id(
    db: Session,
    track_name: str,
    artist_id: int,
    year: Optional[int] = None,
    spotify_track_id: Optional[str] = None,
) -> Optional[int]:
    if not track_name or not artist_id:
        return None

    _set_local_timeouts(db)

    t = track_name.strip()

    # 0) If we have a spotify id, prefer that fast path first
    if spotify_track_id and hasattr(Track, "spotify_track_id"):
        row = db.exec(
            select(Track.id).where(Track.spotify_track_id == spotify_track_id)
        ).first()
        tid = _as_int_id(row)
        if tid:
            return tid

    # 1) Exact match on (name, artist[, year])
    stmt = select(Track.id).where(
        func.lower(Track.track_name) == t.lower(),
        Track.artist_id == artist_id,
    )
    if year is not None and hasattr(Track, "year_released"):
        stmt = stmt.where(Track.year_released == year)

    row = db.exec(stmt).first()
    tid = _as_int_id(row)
    if tid:
        return tid

    # 2) Try to insert
    track = Track(track_name=t, artist_id=artist_id)
    if year is not None and hasattr(Track, "year_released"):
        track.year_released = year
    if spotify_track_id and hasattr(Track, "spotify_track_id"):
        track.spotify_track_id = spotify_track_id
    # Sensible defaults your model expects
    if hasattr(Track, "is_explicit") and getattr(track, "is_explicit", None) is None:
        track.is_explicit = False
    if hasattr(Track, "mode_flag") and getattr(track, "mode_flag", None) is None:
        track.mode_flag = "SOLO"
    if hasattr(Track, "language") and getattr(track, "language", None) is None:
        track.language = "en"

    db.add(track)
    try:
        db.flush()
        return track.id

    except IntegrityError:
        # Unique collision (likely spotify_track_id); reselect deterministically
        db.rollback()
        if spotify_track_id and hasattr(Track, "spotify_track_id"):
            row = db.exec(
                select(Track.id).where(Track.spotify_track_id == spotify_track_id)
            ).first()
            tid = _as_int_id(row)
            if tid:
                return tid
        # Fall back to exact match by (name, artist[, year])
        row = db.exec(stmt).first()
        return _as_int_id(row)

    except OperationalError:
        # e.g. "canceling statement due to statement timeout" while building the unique index entry
        db.rollback()
        # Re-check: if the other txn committed, the row should be visible now
        if spotify_track_id and hasattr(Track, "spotify_track_id"):
            row = db.exec(
                select(Track.id).where(Track.spotify_track_id == spotify_track_id)
            ).first()
            tid = _as_int_id(row)
            if tid:
                return tid
        row = db.exec(stmt).first()
        tid = _as_int_id(row)
        if tid:
            return tid
        # As a last attempt, try one more insert
        track = Track(track_name=t, artist_id=artist_id)
        if year is not None and hasattr(Track, "year_released"):
            track.year_released = year
        if spotify_track_id and hasattr(Track, "spotify_track_id"):
            track.spotify_track_id = spotify_track_id
        if hasattr(Track, "is_explicit"):
            track.is_explicit = False
        if hasattr(Track, "mode_flag"):
            track.mode_flag = "SOLO"
        if hasattr(Track, "language"):
            track.language = "en"
        db.add(track)
        try:
            db.flush()
            return track.id
        except Exception:
            db.rollback()
            return None


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
