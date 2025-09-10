# backend/routers/collections.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from sqlalchemy import delete

from backend.database import get_db
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track
from backend.schemas.collection_schemas import (
    CollectionImportPayload, ImportResult,
    CollectionExport, CollectionExportTrack, CollectionIn
)
from backend.services.track_resolver import resolve_track_id_by_meta

router = APIRouter(prefix="/collections", tags=["Collections"])
@router.post("/import-json", response_model=ImportResult)
def import_collection(payload: CollectionImportPayload, db: Session = Depends(get_db)):
    c_in = payload.collection

    # 1) Upsert collection by slug
    coll = db.exec(select(Collection).where(Collection.slug == c_in.slug)).first()
    if not coll:
        coll = Collection(name=c_in.name, slug=c_in.slug, collection_type=c_in.type)
        db.add(coll)
        db.commit()
        db.refresh(coll)
    else:
        dirty = False
        if coll.name != c_in.name:
            coll.name = c_in.name; dirty = True
        if coll.collection_type != c_in.type:
            coll.collection_type = c_in.type; dirty = True
        # (optional) update intro if provided
        if hasattr(c_in, "intro") and c_in.intro is not None and getattr(coll, "intro", None) != c_in.intro:
            coll.intro = c_in.intro; dirty = True
        if dirty:
            db.add(coll); db.commit(); db.refresh(coll)

    # 2) Cache existing ranks
    existing = {
        r.ranking: r for r in db.exec(
            select(CollectionTrackRanking).where(CollectionTrackRanking.collection_id == coll.id)
        ).all()
    }

    # 3) Pre-validate incoming payload (duplicate ranks)
    seen = set()
    dup_ranks = []
    for it in payload.tracks:
        if it.ranking in seen:
            dup_ranks.append(it.ranking)
        else:
            seen.add(it.ranking)

    if dup_ranks:
        raise HTTPException(status_code=400, detail={
            "message": "Duplicate rankings in payload",
            "ranks": sorted(set(dup_ranks))
        })
    inserted = updated = 0
    unresolved: list[dict] = []
    to_upsert: list[CollectionTrackRanking] = []

    # 4) Resolve all first (trackId → spotifyTrackId → title+artist(+year))
    incoming_ranks = set()
    for item in payload.tracks:
        incoming_ranks.add(item.ranking)

        track_id = None

        # a) direct trackId
        if getattr(item, "trackId", None):
            track_id = item.trackId if db.get(Track, item.trackId) else None
            if track_id is None:
                unresolved.append({"ranking": item.ranking, "reason": "trackId not found", "trackId": item.trackId})
                continue

        # b) spotifyTrackId (if your Track has this column)
        if track_id is None and getattr(item, "spotifyTrackId", None):
            tid = db.exec(select(Track.id).where(Track.spotify_track_id == item.spotifyTrackId)).scalar_one_or_none()
            if tid:
                track_id = tid

        # c) fallback: title + artist (+ year)
        if track_id is None:
            track_id = resolve_track_id_by_meta(db, item.title, item.artistName, getattr(item, "year", None))
            if not track_id:
                unresolved.append({
                    "ranking": item.ranking,
                    "title": getattr(item, "title", None),
                    "artistName": getattr(item, "artistName", None),
                    "year": getattr(item, "year", None),
                    "spotifyTrackId": getattr(item, "spotifyTrackId", None),
                    "reason": "no match"
                })
                continue

        # Merge/Upsert into the in-memory list
        if item.ranking in existing:
            row = existing[item.ranking]
            changed = False
            if row.track_id != track_id:
                row.track_id = track_id; changed = True
            # optional per-rank note
            if hasattr(item, "note") and item.note is not None and getattr(row, "note", None) != item.note:
                row.note = item.note; changed = True
            if changed:
                to_upsert.append(row); updated += 1
        else:
            row = CollectionTrackRanking(collection_id=coll.id, track_id=track_id, ranking=item.ranking)
            if hasattr(item, "note") and item.note:
                row.note = item.note
            to_upsert.append(row); inserted += 1

    # 5) strict/dry-run behaviors
    unresolved = sorted(unresolved, key=lambda d: d["ranking"])
    if payload.strict and unresolved:
        raise HTTPException(status_code=400, detail={"message": "Unresolved items", "unresolved": unresolved})

    if payload.dry_run:
        return ImportResult(
            collectionId=coll.id,
            inserted=inserted,
            updated=updated,
            unresolved=unresolved,
            totalIncoming=len(payload.tracks),
            dry_run=True
        )

    # 6) Commit atomically (and optional replace)
    try:
        with db:
            for row in to_upsert:
                db.add(row)
            db.commit()

            # optional: replace mode to prune ranks not in payload
            if getattr(payload, "replace", False):
                ranking_col = CollectionTrackRanking.__table__.c.ranking  # real SA Column
                db.exec(
                    delete(CollectionTrackRanking).where(
                        CollectionTrackRanking.collection_id == coll.id,
                        ~ranking_col.in_(list(incoming_ranks))  # or: ranking_col.notin_(list(incoming_ranks))
                    )
                )
                db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import failed: {e}")

    return ImportResult(
        collectionId=coll.id,
        inserted=inserted,
        updated=updated,
        unresolved=unresolved,
        totalIncoming=len(payload.tracks),
        dry_run=False
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
        tracks.append(CollectionExportTrack(
            ranking=ctr.ranking,
            trackId=t.id,
            title=t.track_name,  # <- was t.title
            artistName=t.artist_name,
            year=getattr(t, "release_year", None)
        ))

    c_out = CollectionIn(name=coll.name, slug=coll.slug, type=coll.collection_type)
    return CollectionExport(collection=c_out, tracks=tracks)
