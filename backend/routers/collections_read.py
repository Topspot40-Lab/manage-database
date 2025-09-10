# backend/routers/collections_read.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlmodel import Session, text
from backend.database import get_db

router = APIRouter(prefix="/collections-read", tags=["Collections (Unified Read)"])

def _sch(db: Session) -> str:
    """Return 'public.' for Postgres; '' otherwise (silences linters on non-PG)."""
    try:
        return "public." if db.get_bind().dialect.name.startswith("postgres") else ""
    except Exception:
        return ""

@router.get("", summary="List all collections (legacy + new)")
def list_collections(
    type: Optional[str] = Query(None, description="'DECADE_GENRE' or 'SPECIALTY'"),
    q: Optional[str] = Query(None, description="Filter by name (ILIKE)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    sch = _sch(db)
    sql = f"SELECT * FROM {sch}v_collections_unified"
    conds, params = [], {}

    if type:
        conds.append("collection_type = :ctype")
        params["ctype"] = type
    if q:
        conds.append("name ILIKE :q")
        params["q"] = f"%{q}%"

    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY is_legacy DESC, name LIMIT :limit OFFSET :offset"

    params.update({"limit": limit, "offset": offset})

    rows = db.exec(text(sql), params=params).mappings().all()
    return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset, "count": len(rows)}

@router.get("/{slug}/tracks", summary="Get ranked tracks for a collection (legacy + new)")
def get_collection_tracks(slug: str, db: Session = Depends(get_db)):
    sch = _sch(db)

    row = db.exec(
        text(f"SELECT * FROM {sch}v_collections_unified WHERE slug = :slug LIMIT 1"),
        params={"slug": slug}
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Collection not found")

    tracks = db.exec(
        text(f"""
            SELECT v.ranking,
                   t.id           AS track_id,
                   t.track_name   AS title,
                   t.artist_name  AS artist_name,
                   t.release_year AS release_year
            FROM {sch}v_collection_tracks_unified v
            JOIN {sch}track t ON t.id = v.track_id
            WHERE v.collection_id = :cid
            ORDER BY v.ranking

        """),
        params={"cid": row["collection_id"]}
    ).mappings().all()

    return {"collection": dict(row), "tracks": [dict(t) for t in tracks]}
