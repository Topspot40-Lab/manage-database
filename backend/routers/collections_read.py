# backend/routers/collections_read.py
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, text
from backend.database import get_db
import logging

log = logging.getLogger(__name__)
router = APIRouter(tags=["Supabase: Collections"], prefix="/supabase/collections")

def _is_postgres(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name.startswith("postgres")
    except Exception:
        return False

def _schema_prefix(db: Session) -> str:
    return "public." if _is_postgres(db) else ""

def _table_has_column(db: Session, table_name: str, col: str) -> bool:
    sch_name = "public" if _is_postgres(db) else "main"  # 'main' is harmless for SQLite
    stmt = text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t AND column_name = :c
        LIMIT 1
    """).bindparams(s=sch_name, t=table_name, c=col)
    try:
        return db.exec(stmt).first() is not None
    except Exception:
        # SQLite doesn’t have information_schema; fall back to PRAGMA
        if not _is_postgres(db):
            try:
                pragma = text(f"PRAGMA table_info({table_name})")
                cols = [r[1] for r in db.exec(pragma).all()]  # (cid, name, type, notnull, dflt_value, pk)
                return col in cols
            except Exception:
                return False
        return False

@router.get("", summary="List all collections (base table only)")
def list_collections(
    type: Optional[str] = Query(None, description="Legacy filter: 'DECADE_GENRE' or 'COLLECTION'"),
    q: Optional[str] = Query(None, description="Filter by name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    sch = _schema_prefix(db)
    is_pg = _is_postgres(db)
    has_type = _table_has_column(db, "collection", "collection_type")

    try:
        type_expr = "c.collection_type AS collection_type" if has_type else (
            "'COLLECTION'::text AS collection_type" if is_pg else "'COLLECTION' AS collection_type"
        )

        select_cols = [
            "c.id   AS collection_id",
            "c.name",
            "c.slug",
            "c.intro",
            type_expr,
            "FALSE AS is_legacy",
        ]
        sql = f"SELECT\n  " + ",\n  ".join(select_cols) + f"\nFROM {sch}collection c"

        conds = []
        params = {"limit": limit, "offset": offset}

        if q:
            if is_pg:
                conds.append("c.name ILIKE :q")
            else:
                conds.append("LOWER(c.name) LIKE LOWER(:q)")
            params["q"] = f"%{q}%"

        if type:
            if has_type:
                conds.append("c.collection_type = :ctype")
                params["ctype"] = type
            else:
                # Without the column, we cannot distinguish; return empty for DECADE_GENRE
                if type.upper() == "DECADE_GENRE":
                    return {"items": [], "limit": limit, "offset": offset, "count": 0}

        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY c.name LIMIT :limit OFFSET :offset"

        rows = db.exec(text(sql).bindparams(**params)).mappings().all()
        return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset, "count": len(rows)}

    except Exception as e:
        log.exception("collections_read.list_collections failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{slug}/tracks", summary="Get ranked tracks for a collection (base tables)")
def get_collection_tracks(slug: str, db: Session = Depends(get_db)):
    sch = _schema_prefix(db)
    is_pg = _is_postgres(db)
    has_type = _table_has_column(db, "collection", "collection_type")

    try:
        type_expr = "c.collection_type AS collection_type" if has_type else (
            "'COLLECTION'::text AS collection_type" if is_pg else "'COLLECTION' AS collection_type"
        )

        stmt = text(f"""
            SELECT
              c.id   AS collection_id,
              c.name AS name,
              c.slug AS slug,
              c.intro AS intro,
              {type_expr},
              FALSE AS is_legacy
            FROM {sch}collection c
            WHERE c.slug = :slug
            LIMIT 1
        """).bindparams(slug=slug)

        row = db.exec(stmt).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Ranked tracks + note (ctr.intro)
        stmt_tracks = text(f"""
            SELECT
              r.ranking,
              r.intro              AS note,
              t.id                 AS track_id,
              t.track_name         AS title,
              t.artist_display_name AS artist_name,
              t.album_name         AS album_name
            FROM {sch}collection_track_ranking r
            JOIN {sch}track t ON t.id = r.track_id
            WHERE r.collection_id = :cid
            ORDER BY r.ranking
        """).bindparams(cid=row["collection_id"])

        tracks = db.exec(stmt_tracks).mappings().all()
        return {"collection": dict(row), "tracks": [dict(t) for t in tracks]}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("collections_read.get_collection_tracks failed")
        raise HTTPException(status_code=500, detail=str(e))
