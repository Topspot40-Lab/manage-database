# backend/routers/collections.py
from __future__ import annotations

import os
import inspect
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlmodel import Session, select

from backend.database import get_db
from backend.models.collection_models import (
    Collection, CollectionTrackRanking,
)
from backend.models.dbmodels import Track
from backend.schemas.collection_schemas import (
    CollectionImportPayload, ImportResult,
    CollectionExport, CollectionExportTrack, CollectionIn
)
from backend.services.track_resolver import resolve_track_id_by_meta

# Use namespaced logger so it respects LOG_LEVELS_BY_MODULE["backend.routers.collections"]
logger = logging.getLogger(__name__)

# Show source path for the Collection model (debug by default; opt-in to INFO via env)
try:
    _src = inspect.getfile(Collection)
    if os.getenv("SHOW_COLLECTIONS_SRC", "").lower() in ("1", "true", "yes", "on"):
        logger.info("USING Collection from %s", _src)
    else:
        logger.debug("USING Collection from %s", _src)
except Exception:
    # Avoid any import-time failures just from logging
    logger.debug("Could not determine Collection model source path", exc_info=True)

router = APIRouter(prefix="/collections")


@router.post("/import-json", response_model=ImportResult)
def import_collection(payload: CollectionImportPayload, db: Session = Depends(get_db)):
    try:
        c_in = payload.collection
        skip_resolve = bool(getattr(payload, "skipResolve", False))

        # 1) Upsert collection by slug
        coll = db.exec(select(Collection).where(Collection.slug == c_in.slug)).first()
        if not coll:
            coll = Collection(name=c_in.name, slug=c_in.slug, intro=getattr(c_in, "intro", None))
            db.add(coll); db.commit(); db.refresh(coll)
        else:
            dirty = False
            if coll.name != c_in.name:
                coll.name = c_in.name; dirty = True
            if hasattr(c_in, "intro") and c_in.intro is not None and getattr(coll, "intro", None) != c_in.intro:
                coll.intro = c_in.intro; dirty = True
            if dirty:
                db.add(coll); db.commit(); db.refresh(coll)

        # 2) Cache existing ranks
        existing = {
            r.ranking: r
            for r in db.exec(
                select(CollectionTrackRanking).where(CollectionTrackRanking.collection_id == coll.id)
            ).all()
        }

        # 3) Pre-validate incoming payload (duplicate ranks)
        seen = set(); dup_ranks = []
        for it in payload.tracks:
            if it.ranking in seen: dup_ranks.append(it.ranking)
            else: seen.add(it.ranking)
        if dup_ranks:
            raise HTTPException(status_code=400, detail={
                "message": "Duplicate rankings in payload", "ranks": sorted(set(dup_ranks))
            })

        inserted = updated = 0
        unresolved: list[dict] = []
        to_upsert: list[CollectionTrackRanking] = []
        incoming_ranks = {it.ranking for it in payload.tracks}

        # ---------- helper to resolve a single item ----------
        def resolve_for_item(it) -> tuple[int | None, dict | None]:
            """Return (track_id, unresolved_dict). Exactly one of them is non-None."""
            # a) direct trackId
            tid = getattr(it, "trackId", None)
            if tid is not None:
                if db.get(Track, tid):
                    return tid, None
                return None, {"ranking": it.ranking, "reason": "trackId not found", "trackId": tid}

            # b) DB lookup by spotifyTrackId
            spid = getattr(it, "spotifyTrackId", None)
            if spid:
                found = db.exec(select(Track.id).where(Track.spotify_track_id == spid)).scalar_one_or_none()
                if found:
                    return found, None
                # fall through to metadata/skip

            # c) metadata resolution (optional)
            title = getattr(it, "title", None)
            artist = getattr(it, "artistName", None)
            year = getattr(it, "year", None)

            if skip_resolve:
                return None, {
                    "ranking": it.ranking,
                    "title": title, "artistName": artist, "year": year,
                    "spotifyTrackId": spid, "reason": "skipped resolution"
                }

            try:
                resolved = resolve_track_id_by_meta(db, title, artist, year)
            except Exception as e:
                logger.warning("resolve_track_id_by_meta failed (rank=%s): %s", it.ranking, e)
                resolved = None
            if resolved:
                return resolved, None

            return None, {
                "ranking": it.ranking,
                "title": title, "artistName": artist, "year": year,
                "spotifyTrackId": spid, "reason": "no match"
            }

        # ---------- main loop ----------
        for item in payload.tracks:
            track_id, unresolved_rec = resolve_for_item(item)
            if unresolved_rec is not None:
                unresolved.append(unresolved_rec)
                continue

            # Schema already maps legacy 'note' -> 'intro' (validation_alias), so just use intro
            blurb = getattr(item, "intro", None)

            if item.ranking in existing:
                row = existing[item.ranking]
                changed = False
                if row.track_id != track_id:
                    row.track_id = track_id; changed = True
                if blurb is not None and getattr(row, "intro", None) != blurb:
                    row.intro = blurb; changed = True
                if changed:
                    to_upsert.append(row); updated += 1
            else:
                row = CollectionTrackRanking(collection_id=coll.id, track_id=track_id, ranking=item.ranking)
                if blurb:
                    row.intro = blurb
                to_upsert.append(row); inserted += 1

        # 5) strict/dry-run
        unresolved.sort(key=lambda d: d["ranking"])
        if payload.strict and unresolved:
            raise HTTPException(status_code=400, detail={"message": "Unresolved items", "unresolved": unresolved})
        if payload.dry_run:
            return ImportResult(
                collectionId=coll.id, inserted=inserted, updated=updated,
                unresolved=unresolved, totalIncoming=len(payload.tracks), dry_run=True
            )

        # 6) Commit (+ optional replace)
        try:
            for row in to_upsert:
                db.add(row)
            db.commit()
            if getattr(payload, "replace", False):
                ranking_col = CollectionTrackRanking.__table__.c.ranking
                db.exec(
                    delete(CollectionTrackRanking).where(
                        CollectionTrackRanking.collection_id == coll.id,
                        ~ranking_col.in_(list(incoming_ranks)),
                    )
                )
                db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Import failed: {e}")

        return ImportResult(
            collectionId=coll.id, inserted=inserted, updated=updated,
            unresolved=unresolved, totalIncoming=len(payload.tracks), dry_run=False
        )

    except Exception as e:
        src = inspect.getfile(Collection)
        logger.exception("import-json failed; Collection from %s", src)
        raise HTTPException(
            status_code=500,
            detail={"error": f"{type(e).__name__}: {e}", "collection_model_source": src}
        )


@router.get("/{slug}/export-json", response_model=CollectionExport)
def export_collection(slug: str, db: Session = Depends(get_db)):
    coll = db.exec(select(Collection).where(Collection.slug == slug)).first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")

    rows = db.exec(
        select(CollectionTrackRanking, Track)
        .join(Track, Track.id == CollectionTrackRanking.track_id)
        .where(CollectionTrackRanking.collection_id == coll.id)
        .order_by(CollectionTrackRanking.ranking)
    ).all()

    tracks: List[CollectionExportTrack] = []
    for ctr, t in rows:
        artist_name = getattr(t, "artist_display_name", None)
        if not artist_name and hasattr(t, "artist") and t.artist:
            artist_name = getattr(t.artist, "artist_name", None)

        tracks.append(CollectionExportTrack(
            ranking=ctr.ranking,
            trackId=t.id,
            title=(getattr(t, "track_name", None) or getattr(t, "title", None) or ""),
            artistName=artist_name or "",
            year=getattr(t, "year_released", None),
            intro=getattr(ctr, "intro", None),
        ))

    c_out = CollectionIn(name=coll.name, slug=coll.slug, intro=getattr(coll, "intro", None))
    return CollectionExport(collection=c_out, tracks=tracks)
