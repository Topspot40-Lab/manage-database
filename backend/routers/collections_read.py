
# backend/routers/collections_read.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlmodel import Session, text
from backend.database import get_db
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/collections-read", tags=["Collections (Unified Read)"])

def _sch(db: Session) -> str:
    try:
        return "public." if db.get_bind().dialect.name.startswith("postgres") else ""
    except Exception:
        return ""

def _table_has_column(db: Session, table_name: str, col: str) -> bool:
    sch_name = _sch(db).rstrip(".") or "public"
    stmt = text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t AND column_name = :c
    """).bindparams(s=sch_name, t=table_name, c=col)
    return db.exec(stmt).first() is not None

@router.get("", summary="List all collections (base table only)")
def list_collections(
    type: Optional[str] = Query(None, description="'DECADE_GENRE' or 'COLLECTION'"),
    q: Optional[str] = Query(None, description="Filter by name (ILIKE)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    sch = _sch(db)
    has_type = _table_has_column(db, "collection", "collection_type")

    try:
        # Select the columns we have; project a constant type if column is missing
        select_cols = [
            "c.id   AS collection_id",
            "c.name",
            "c.slug",
            ("c.collection_type" if has_type else "'COLLECTION'::text AS collection_type"),
            "FALSE AS is_legacy",
        ]
        sql = f"SELECT\n  " + ",\n  ".join(select_cols) + f"\nFROM {sch}collection c"

        conds = []
        params = {}
        if q:
            conds.append("c.name ILIKE :q")
            params["q"] = f"%{q}%"

        if type:
            if has_type:
                conds.append("c.collection_type = :ctype")
                params["ctype"] = type
            else:
                # Without the column, we can only return COLLECTION rows; DECADE_GENRE yields empty
                if type.upper() == "DECADE_GENRE":
                    return {"items": [], "limit": limit, "offset": offset, "count": 0}

        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += f" ORDER BY c.name LIMIT {int(limit)} OFFSET {int(offset)}"

        rows = db.exec(text(sql).bindparams(**params)).mappings().all()
        return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset, "count": len(rows)}
    except Exception as e:
        log.exception("collections_read.list_collections failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{slug}/tracks", summary="Get ranked tracks for a collection (base tables)")
def get_collection_tracks(slug: str, db: Session = Depends(get_db)):
    sch = _sch(db)
    has_type = _table_has_column(db, "collection", "collection_type")

    try:
        # Get the collection row
        if has_type:
            stmt = text(f"""
                SELECT
                  c.id   AS collection_id,
                  c.name AS name,
                  c.slug AS slug,
                  c.collection_type AS collection_type,
                  FALSE AS is_legacy
                FROM {sch}collection c
                WHERE c.slug = :slug
                LIMIT 1
            """).bindparams(slug=slug)
        else:
            stmt = text(f"""
                SELECT
                  c.id   AS collection_id,
                  c.name AS name,
                  c.slug AS slug,
                  'COLLECTION'::text AS collection_type,
                  FALSE AS is_legacy
                FROM {sch}collection c
                WHERE c.slug = :slug
                LIMIT 1
            """).bindparams(slug=slug)

        row = db.exec(stmt).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Pull tracks from ranking + track
        stmt_tracks = text(f"""
            SELECT
              r.ranking,
              t.id                   AS track_id,
              t.track_name           AS title,
              t.artist_display_name  AS artist_name,
              t.album_name           AS album_name
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
