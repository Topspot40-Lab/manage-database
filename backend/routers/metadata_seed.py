from __future__ import annotations
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database import get_db
# Assumes these exist; adjust import paths/names if needed:
from backend.models.decade_models import Decade  # id, slug UNIQUE, description
from backend.models.genre_models import Genre    # id, slug UNIQUE, description
from backend.models.decade_genre_models import DecadeGenre  # decade_id, genre_id, description, UNIQUE(decade_id, genre_id)
from backend.schemas.metadata_schemas import SeedDoc

router = APIRouter(prefix="/metadata", tags=["metadata"])

@router.post("/seed")
def seed_metadata(doc: SeedDoc, db: Session = Depends(get_db)):
    # --- Upsert decades ---
    for d in doc.decades:
        row = db.exec(select(Decade).where(Decade.slug == d.slug)).first()
        if row:
            if d.description is not None and row.description != d.description:
                row.description = d.description
                db.add(row)
        else:
            db.add(Decade(slug=d.slug, description=d.description))
    # --- Upsert genres ---
    for g in doc.genres:
        row = db.exec(select(Genre).where(Genre.slug == g.slug)).first()
        if row:
            if g.description is not None and row.description != g.description:
                row.description = g.description
                db.add(row)
        else:
            db.add(Genre(slug=g.slug, description=g.description))

    # Persist so new ids exist
    db.commit()

    # Build slug -> id maps
    dec_map: Dict[str, int] = {d.slug: d.id for d in db.exec(select(Decade)).all()}
    gen_map: Dict[str, int] = {g.slug: g.id for g in db.exec(select(Genre)).all()}

    missing_pairs: List[dict] = []
    inserted = updated = 0

    # --- Upsert decade_genre combos ---
    for c in doc.decade_genre:
        did = dec_map.get(c.decade)
        gid = gen_map.get(c.genre)
        if not did or not gid:
            missing_pairs.append({"decade": c.decade, "genre": c.genre})
            continue

        row = db.exec(
            select(DecadeGenre).where(
                (DecadeGenre.decade_id == did) & (DecadeGenre.genre_id == gid)
            )
        ).first()

        if row:
            new_desc = c.description or row.description
            if new_desc != row.description:
                row.description = new_desc
                db.add(row)
                updated += 1
        else:
            db.add(DecadeGenre(decade_id=did, genre_id=gid, description=c.description))
            inserted += 1

    db.commit()

    return {
        "decades_seen": len(doc.decades),
        "genres_seen": len(doc.genres),
        "combos_seen": len(doc.decade_genre),
        "combos_inserted": inserted,
        "combos_updated": updated,
        "missing_pairs": missing_pairs,
    }
