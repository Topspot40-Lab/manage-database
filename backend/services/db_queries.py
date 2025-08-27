# backend/services/db_queries.py
from __future__ import annotations

from sqlmodel import Session, select
from typing import Optional, List, Tuple
from sqlalchemy import func
import logging
from time import perf_counter

from backend.models import Track, TrackRanking, DecadeGenre, Decade, Genre, Artist

# Use a stable module logger so config.LOG_LEVELS_BY_MODULE can target it:
logger = logging.getLogger("backend.services.db_queries")


def _compile_sql(stmt, db: Session) -> str:
    """
    Best-effort SQL string with literal binds when possible.
    Falls back to str(stmt) if dialect/bind isn't available.
    """
    try:
        bind = db.get_bind()
        return str(
            stmt.compile(
                dialect=bind.dialect,
                compile_kwargs={"literal_binds": True},
            )
        )
    except Exception:
        # Placeholders-only SQL as a fallback
        return str(stmt)


def get_decade_genre(db: Session, decade: str, genre: str) -> Optional[DecadeGenre]:
    stmt = (
        select(DecadeGenre)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .where(Decade.decade_name == decade)
        .where(Genre.genre_name == genre)
    )

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("get_decade_genre SQL:\n%s", _compile_sql(stmt, db))

    t0 = perf_counter()
    row = db.exec(stmt).first()
    ms = (perf_counter() - t0) * 1000.0

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "get_decade_genre(decade=%r, genre=%r) -> %s (%.1f ms)",
            decade,
            genre,
            f"DecadeGenre(id={row.id})" if row else None,
            ms,
        )
    return row


def get_rankings_for_combo(db: Session, decade_genre_id: int) -> List[TrackRanking]:
    stmt = select(TrackRanking).where(TrackRanking.decade_genre_id == decade_genre_id)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("get_rankings_for_combo SQL:\n%s", _compile_sql(stmt, db))

    t0 = perf_counter()
    rows = db.exec(stmt).all()
    ms = (perf_counter() - t0) * 1000.0

    if logger.isEnabledFor(logging.DEBUG):
        ranks = [r.ranking for r in rows]
        logger.debug(
            "get_rankings_for_combo(dg_id=%s) -> %d rows; ranks=%s (%.1f ms)",
            decade_genre_id,
            len(rows),
            ranks[:10] + (["…"] if len(ranks) > 10 else []),
            ms,
        )
    return rows


def get_random_track(db: Session) -> Optional[Track]:
    # Prefer tracks with spotify ids so playback works
    stmt = (
        select(Track)
        .where(Track.spotify_track_id.isnot(None))
        .order_by(func.random())
        .limit(1)
    )

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("get_random_track SQL:\n%s", _compile_sql(stmt, db))

    t0 = perf_counter()
    row = db.exec(stmt).first()
    ms = (perf_counter() - t0) * 1000.0

    if logger.isEnabledFor(logging.DEBUG):
        if row:
            logger.debug(
                "get_random_track -> Track(id=%s, name=%r, spotify_track_id=%r) (%.1f ms)",
                row.id,
                row.track_name,
                row.spotify_track_id,
                ms,
            )
        else:
            logger.debug("get_random_track -> None (%.1f ms)", ms)
    return row


def get_rankings_for_track(db: Session, track_id: int) -> List[Tuple[TrackRanking, str, str]]:
    """
    Returns [(TrackRanking, decade_name, genre_name), ...] for the given track.
    Also logs an INFO summary indicating whether anything was found.
    """
    stmt = (
        select(TrackRanking, Decade.decade_name, Genre.genre_name)
        .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .where(TrackRanking.track_id == track_id)
        .order_by(Decade.decade_name, Genre.genre_name, TrackRanking.ranking)
    )

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("get_rankings_for_track SQL:\n%s", _compile_sql(stmt, db))

    t0 = perf_counter()
    try:
        rows = db.exec(stmt).all()
    except Exception as e:
        # Surface query issues loudly
        logger.exception("get_rankings_for_track(track_id=%s) query failed: %s", track_id, e)
        return []
    ms = (perf_counter() - t0) * 1000.0

    # Summarize results
    count   = len(rows)
    decades = sorted({d for (_tr, d, _g) in rows}) if rows else []
    genres  = sorted({g for (_tr, _d, g) in rows}) if rows else []
    ranks   = [tr.ranking for (tr, _d, _g) in rows]

    # INFO: what was found (or not)
    if count == 0:
        logger.info("get_rankings_for_track(track_id=%s): no rankings found (%.1f ms)", track_id, ms)
    else:
        logger.info(
            "get_rankings_for_track(track_id=%s): %d rows | decades=%s | genres=%s | ranks=%s (%.1f ms)",
            track_id,
            count,
            decades,
            genres,
            ranks[:15] + (["…"] if len(ranks) > 15 else []),
            ms,
        )

    # DEBUG: extra detail (optional, keep if useful)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "get_rankings_for_track(track_id=%s) DEBUG: decades=%s; genres=%s; all_ranks=%s",
            track_id, decades, genres, ranks
        )

    return rows


def get_artist_by_id(db: Session, artist_id: int) -> Optional[Artist]:
    t0 = perf_counter()
    row = db.get(Artist, artist_id)
    ms = (perf_counter() - t0) * 1000.0

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "get_artist_by_id(%s) -> %s (%.1f ms)",
            artist_id,
            f"Artist(id={row.id}, name={getattr(row, 'artist_name', None)!r})" if row else None,
            ms,
        )
    return row
