from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import outerjoin, text as sa_text, inspect as sa_inspect

from backend.database import get_db
from backend.models.dbmodels import (
    Track, Artist, TrackRanking, DecadeGenre, Decade, Genre,
)

# Optional locales (won’t crash if absent)
try:
    from backend.models.dbmodels import TrackRankingLocale
    HAS_TR_LOCALE = True
except Exception:
    TrackRankingLocale = None  # type: ignore
    HAS_TR_LOCALE = False

from backend.services.ads.script_generator import TrackAdInputs, generate_ad_script
from backend.services.ads.ad_audio import build_ad_script_and_mp3_by_track

logger = logging.getLogger("backend.routers.ads_scripts")

# Prefer Track.track_name, with safe fallbacks
TRACK_TITLE_FIELDS = ("track_name", "title", "name", "track_title", "display_title")

router = APIRouter(prefix="/ads", tags=["Ads / Scripts"])

# --------------------------- helpers ---------------------------

def _safe_get(obj, *names: str, default=None):
    """Return the first present, non-None attribute from names."""
    for n in names:
        if hasattr(obj, n):
            val = getattr(obj, n)
            if val is not None:
                return val
    return default

def _outer_join_graph():
    """Build an OUTER JOIN graph so missing relationships don’t drop the row."""
    oj = outerjoin(
            outerjoin(
                outerjoin(
                    outerjoin(Track, Artist, Track.artist_id == Artist.id),
                    TrackRanking, TrackRanking.track_id == Track.id,
                ),
                DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id,
            ),
            Decade, Decade.id == DecadeGenre.decade_id,
        )
    oj = outerjoin(oj, Genre, Genre.id == DecadeGenre.genre_id)
    return oj

def _get_locale_row(db: Session, ranking_id: int, language: str):
    if not HAS_TR_LOCALE or not TrackRankingLocale:
        return None
    try:
        return db.exec(
            select(TrackRankingLocale).where(
                (TrackRankingLocale.track_ranking_id == ranking_id) &
                (TrackRankingLocale.language == language)
            )
        ).first()
    except Exception:
        return None

def _inputs_from_row(
    track, artist, ranking, decade, genre, *, language: str
) -> TrackAdInputs:
    return TrackAdInputs(
        track_title=_safe_get(track, *TRACK_TITLE_FIELDS, default="(untitled)"),
        artist_name=_safe_get(artist, "name", default="Unknown Artist"),
        year_released=str(_safe_get(track, "release_year", "year"))
            if _safe_get(track, "release_year", "year") is not None else None,
        category=_safe_get(decade, "name", default=None),
        genre=_safe_get(genre, "name", default=None),
        intro_text=_safe_get(ranking, "intro", default=None),
        detail_text=_safe_get(ranking, "detail", default=None),
        rank=_safe_get(ranking, "rank", default=None),
        language=language,
    )

# ------------------------- debug utilities ---------------------

@router.get("/health", summary="Quick health check")
def health():
    return {"ok": True, "router": "ads_scripts"}

@router.get("/debug/track-columns", summary="List Track table columns (mapper)")
def track_columns():
    try:
        cols = list(Track.__table__.columns.keys())  # type: ignore[attr-defined]
    except Exception:
        cols = []
    return {"columns": cols}

@router.get("/debug/db-tables", summary="List DB tables via SQLAlchemy inspector")
def db_tables(db: Session = Depends(get_db)):
    try:
        bind = db.get_bind()
        insp = sa_inspect(bind)
        tables = insp.get_table_names(schema="public") or insp.get_table_names()
    except Exception:
        logger.exception("db-tables introspection failed")
        raise HTTPException(status_code=500, detail="DB introspection failed")
    return {"tables": tables}
from sqlalchemy import func

from sqlalchemy import func, literal

@router.get("/debug/track-count", summary="Count tracks (robust, with fallbacks)")
def track_count(db: Session = Depends(get_db)):
    """
    Attempts, in order:
      1) COUNT(*) using mapped Table (best).
      2) Raw SQL COUNT(*) using the mapped table's schema/name.
      3) Existence probe (lower bound): 0 or ≥1 if a row exists.
    """
    # 1) COUNT(*) via mapped Table object (portable)
    try:
        tbl = Track.__table__  # type: ignore[attr-defined]
        # Some backends are picky; COUNT(1) is widely accepted
        stmt = select(func.count(literal(1))).select_from(tbl)
        cnt = db.exec(stmt).one()[0]
        return {"count": int(cnt), "mode": "table"}
    except Exception:
        logger.exception("track-count table path failed; trying raw SQL")

    # 2) Raw SQL using schema + table name from mapper (quotes for PG/SQLite)
    try:
        bind = db.get_bind()
        tbl = Track.__table__  # type: ignore[attr-defined]
        schema = getattr(tbl, "schema", None)
        name = getattr(tbl, "name", None)
        if not name:
            raise RuntimeError("Mapped table name unavailable")

        # Quote name; include schema if present
        if schema:
            full = f'{schema}."{name}"'
        else:
            full = f'"{name}"'
        res = bind.execute(sa_text(f"SELECT COUNT(*) FROM {full}"))
        cnt = int(res.scalar() or 0)
        return {"count": cnt, "mode": "raw", "table_used": full}
    except Exception:
        logger.exception("track-count raw SQL path failed; trying existence probe")

    # 3) Existence probe: 0 or ≥1 (lower bound, but never errors)
    try:
        any_id = db.exec(select(Track.id).limit(1)).first()
        return {"count_lower_bound": 1 if any_id else 0, "mode": "exists"}
    except Exception:
        logger.exception("track-count existence probe failed")

    raise HTTPException(status_code=500, detail="Could not count Track rows")

@router.get("/debug/sample-track-ids", summary="Fetch a few track IDs you can test with")
def sample_track_ids(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Robust sampler:
      1) Try ORM using Track + known title fields.
      2) If ORM fails, try raw SQL against likely tables/columns.
    """
    # --- Attempt 1: ORM (preferred) ---
    try:
        if hasattr(Track, "track_name"):
            rows = db.exec(
                select(Track.id, getattr(Track, "track_name"))
                .order_by(Track.id.desc())
                .limit(limit)
            ).all()
            out = [{"id": r[0], "title": r[1] or "(untitled)"} for r in rows]
            return {"tracks": out, "mode": "orm-direct"}
        # Fallback: select full objects and compose title in Python
        tracks = db.exec(
            select(Track).order_by(Track.id.desc()).limit(limit)
        ).all()
        out = []
        for t in tracks:
            display = _safe_get(t, *TRACK_TITLE_FIELDS, default="(untitled)")
            out.append({"id": getattr(t, "id", None), "title": display})
        return {"tracks": out, "mode": "orm-objects"}
    except Exception:
        logger.exception("sample-track-ids ORM path failed; trying raw SQL fallback")

    # --- Attempt 2: RAW SQL fallback (Postgres/SQLite friendly) ---
    try:
        bind = db.get_bind()
        insp = sa_inspect(bind)
        tables = insp.get_table_names(schema="public") or insp.get_table_names()

        candidates = []
        for tbl in tables:
            try:
                cols = {c["name"] for c in insp.get_columns(tbl, schema="public")} or \
                       {c["name"] for c in insp.get_columns(tbl)}
            except Exception:
                continue
            if "id" in cols:
                title_col = next((c for c in TRACK_TITLE_FIELDS if c in cols), None)
                if title_col:
                    # Quote Postgres table names in public schema
                    tbl_ref = f'public."{tbl}"' if "public" in (insp.default_schema_name or "public") else tbl
                    candidates.append((tbl_ref, title_col))

        for tbl_ref, title_col in candidates:
            try:
                q = sa_text(f"SELECT id, {title_col} AS title FROM {tbl_ref} ORDER BY id DESC LIMIT :lim")
                rows = bind.execute(q, {"lim": limit}).fetchall()
                if rows:
                    out = [{"id": r[0], "title": r[1] or "(untitled)"} for r in rows]
                    return {"tracks": out, "mode": "raw", "table_used": tbl_ref, "title_col": title_col}
            except Exception:
                continue

        # Hail-mary guesses
        for tbl_ref in ("track", "tracks", 'public."track"', 'public."tracks"'):
            for title_col in TRACK_TITLE_FIELDS:
                try:
                    q = sa_text(f"SELECT id, {title_col} AS title FROM {tbl_ref} ORDER BY id DESC LIMIT :lim")
                    rows = bind.execute(q, {"lim": limit}).fetchall()
                    if rows:
                        out = [{"id": r[0], "title": r[1] or "(untitled)"} for r in rows]
                        return {"tracks": out, "mode": "raw_guess", "table_used": tbl_ref, "title_col": title_col}
                except Exception:
                    pass

    except Exception:
        logger.exception("sample-track-ids RAW path failed")

    raise HTTPException(status_code=500, detail="Query failed for Track (ORM + raw fallbacks exhausted)")

# --------------------------- script endpoints -------------------------

@router.get(
    "/script-by-track/{track_id}",
    summary="Generate a 30s ad script from one track"
)
def script_by_track(
    track_id: int,
    language: str = Query("en"),
    db: Session = Depends(get_db),
):
    """Return a ~30s ad script built from the track + ranking context."""
    try:
        stmt = (
            select(Track, Artist, TrackRanking, DecadeGenre, Decade, Genre)
            .select_from(_outer_join_graph())
            .where(Track.id == track_id)
            .limit(1)
        )
        row = db.exec(stmt).first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Track {track_id} not found")

        track, artist, ranking, dg, decade, genre = row
        inputs = _inputs_from_row(track, artist, ranking, decade, genre, language=language)

        # Locale override, if present
        if _safe_get(ranking, "id"):
            loc = _get_locale_row(db, ranking.id, language)
            if loc:
                inputs.intro_text  = _safe_get(loc, "intro",  default=inputs.intro_text)
                inputs.detail_text = _safe_get(loc, "detail", default=inputs.detail_text)

        payload = generate_ad_script(inputs)
        logger.info("✅ ads.script_by_track track_id=%s secs≈%s",
                    track_id, payload.get("estimated_seconds"))
        return payload

    except HTTPException:
        raise
    except Exception:
        logger.exception("❌ ads.script_by_track failed for track_id=%s", track_id)
        raise HTTPException(status_code=500, detail="Internal error generating ad script")

@router.get(
    "/script-by-rank",
    summary="Generate a 30s ad script by (decade_id, genre_id, rank)"
)
def script_by_rank(
    decade_id: int = Query(...),
    genre_id: int = Query(...),
    rank: int = Query(..., ge=1, le=999),
    language: str = Query("en"),
    db: Session = Depends(get_db),
):
    """Return a ~30s ad script for a specific rank within a decade/genre."""
    try:
        tr = db.exec(
            select(TrackRanking)
            .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
            .where(
                (DecadeGenre.decade_id == decade_id) &
                (DecadeGenre.genre_id == genre_id) &
                (TrackRanking.rank == rank)
            )
            .limit(1)
        ).first()
        if not tr:
            raise HTTPException(status_code=404, detail="No ranking found for that decade/genre/rank")

        stmt = (
            select(Track, Artist, TrackRanking, DecadeGenre, Decade, Genre)
            .select_from(_outer_join_graph())
            .where(TrackRanking.id == tr.id)
            .limit(1)
        )
        row = db.exec(stmt).first()
        if not row:
            raise HTTPException(status_code=404, detail="Unable to load joined rows for ranking")

        track, artist, ranking, dg, decade, genre = row
        inputs = _inputs_from_row(track, artist, ranking, decade, genre, language=language)

        # Locale override, if present
        if _safe_get(ranking, "id"):
            loc = _get_locale_row(db, ranking.id, language)
            if loc:
                inputs.intro_text  = _safe_get(loc, "intro",  default=inputs.intro_text)
                inputs.detail_text = _safe_get(loc, "detail", default=inputs.detail_text)

        payload = generate_ad_script(inputs)
        logger.info("✅ ads.script_by_rank decade_id=%s genre_id=%s rank=%s secs≈%s",
                    decade_id, genre_id, rank, payload.get("estimated_seconds"))
        return payload

    except HTTPException:
        raise
    except Exception:
        logger.exception("❌ ads.script_by_rank failed for decade_id=%s genre_id=%s rank=%s",
                         decade_id, genre_id, rank)
        raise HTTPException(status_code=500, detail="Internal error generating ad script")

# --------------------------- MP3 endpoint -------------------------

@router.post(
    "/make-mp3/by-track/{track_id}",
    summary="Generate ad script + MP3 for a track (optional Supabase upload)"
)
def make_mp3_by_track(
    track_id: int,
    language: str = Query("en"),
    voice_id: Optional[str] = Query(None, description="ElevenLabs voice_id"),
    model_id: Optional[str] = Query(None, description="ElevenLabs model id (optional)"),
    speed: Optional[float] = Query(None, description="TTS speed multiplier (e.g., 0.95 or 1.05)"),
    upload: bool = Query(False, description="Upload to Supabase if configured"),
    bucket: Optional[str] = Query(None, description="Supabase bucket (default 'ads-mp3-files')"),
    key_prefix: str = Query("ads/", description="Supabase key prefix"),
    db: Session = Depends(get_db),
):
    """Synthesize a voiced MP3 ad for the given track. Returns paths and upload info."""
    try:
        out = build_ad_script_and_mp3_by_track(
            db,
            track_id=track_id,
            language=language,
            voice_id=voice_id,
            model_id=model_id,
            speed=speed,
            upload=upload,
            bucket=bucket,
            key_prefix=key_prefix,
        )
        logger.info("🎧 Ad MP3 created for track_id=%s → %s secs=%s",
                    track_id, out["local_mp3"], out["estimated_seconds"])
        return out

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=400, detail=str(re))
    except Exception:
        logger.exception("❌ make_mp3_by_track failed (track_id=%s)", track_id)
        raise HTTPException(status_code=500, detail="Failed to create ad MP3")
