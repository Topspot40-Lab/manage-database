# backend/services/collection_import/payload_importer.py
from __future__ import annotations
from typing import List
from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy import delete

from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track
from backend.schemas.collection_schemas import CollectionImportPayload, ImportResult, CollectionIn
from backend.services.track_resolver import resolve_track_id_by_meta, ensure_track_for_meta
from backend.services.collection_import.normalizers import coerce_row, as_int_id


def import_payload(db: Session, payload: CollectionImportPayload) -> ImportResult:
    """Import a payload of tracks into a collection."""
    c_in = payload.collection
    coll = db.exec(select(Collection).where(Collection.slug == c_in.slug)).first()
    if not coll:
        raise HTTPException(status_code=404, detail=f"Collection {c_in.slug} not found")

    existing = {
        r.ranking: r
        for r in db.exec(
            select(CollectionTrackRanking).where(CollectionTrackRanking.collection_id == coll.id)
        ).all()
    }

    inserted = updated = 0
    unresolved = []
    to_upsert: List[CollectionTrackRanking] = []
    incoming_ranks = {it.ranking for it in payload.tracks}

    def resolve_for_item(it):
        raw = it.dict() if hasattr(it, "dict") else dict(it)
        tid = as_int_id(raw.get("trackId"))
        spid = raw.get("spotifyTrackId") or raw.get("spotify_track_id")
        if tid and db.get(Track, tid):
            return tid, None
        if spid:
            found_row = db.exec(select(Track.id).where(Track.spotify_track_id == spid)).first()
            found = as_int_id(found_row)
            if found:
                return found, None
        norm = coerce_row(raw)
        track_name, artist_name, year = norm.get("track_name"), norm.get("artist_name"), norm.get("year_released")
        resolved = resolve_track_id_by_meta(db, track_name, artist_name, year)
        if isinstance(resolved, int):
            return resolved, None
        return None, {"ranking": raw.get("ranking"), "reason": "no match"}

    for item in payload.tracks:
        track_id, unresolved_rec = resolve_for_item(item)
        if unresolved_rec:
            unresolved.append(unresolved_rec)
            continue

        # ✅ Duplicate Track ID protection (allows repeat artists)
        if track_id:
            existing_spid = db.exec(select(Track.spotify_track_id).where(Track.id == track_id)).first()
            if existing_spid:
                duplicate_ctr = db.exec(
                    select(CollectionTrackRanking)
                    .join(Track, Track.id == CollectionTrackRanking.track_id)
                    .where(
                        CollectionTrackRanking.collection_id == coll.id,
                        Track.spotify_track_id == existing_spid,
                    )
                ).first()
                if duplicate_ctr:
                    print(f"⚠️ Skipping duplicate Spotify track {existing_spid}")
                    continue

        blurb = getattr(item, "intro", None)

        if item.ranking in existing:
            row = existing[item.ranking]
            changed = False
            if row.track_id != track_id:
                row.track_id = track_id
                changed = True
            if blurb is not None and getattr(row, "intro", None) != blurb:
                row.intro = blurb
                changed = True
            if changed:
                to_upsert.append(row)
                updated += 1
        else:
            row = CollectionTrackRanking(collection_id=coll.id, track_id=track_id, ranking=item.ranking)
            if blurb:
                row.intro = blurb
            to_upsert.append(row)
            inserted += 1

    try:
        for row in to_upsert:
            db.add(row)
        db.commit()
        if getattr(payload, "replace", False):
            db.exec(
                delete(CollectionTrackRanking).where(
                    CollectionTrackRanking.collection_id == coll.id,
                    ~CollectionTrackRanking.ranking.in_(list(incoming_ranks)),
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
        dry_run=False,
    )
