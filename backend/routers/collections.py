# backend/routers/collections.py
from __future__ import annotations

import json
from pathlib import Path
import backend.config as cfg


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

from backend.services.track_resolver import (
    resolve_track_id_by_meta,
    ensure_track_for_meta,
)


# Use namespaced logger so it respects LOG_LEVELS_BY_MODULE["backend.routers.collections"]
logger = logging.getLogger(__name__)

# add near the top
import unicodedata
from typing import Any, Dict

CANON_KEYS = {
    # title
    "title": "track_name",
    "track": "track_name",
    "trackTitle": "track_name",
    "track_title": "track_name",
    "trackName": "track_name",
    "track_name": "track_name",
    # artist
    "artist": "artist_name",
    "artistName": "artist_name",
    "artist_name": "artist_name",
    "artistDisplayName": "artist_name",
    "artist_display_name": "artist_name",
    # year
    "year": "year_released",
    "yearReleased": "year_released",
    "year_released": "year_released",
}

SMART_APOS = {"\u2019": "'", "\u2018": "'"}

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )

def coerce_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        canon = CANON_KEYS.get(k, k)
        out[canon] = v
    # fix smart quotes/apostrophes and trim
    tn = (out.get("track_name") or "").strip()
    an = (out.get("artist_name") or "").strip()
    for bad, good in SMART_APOS.items():
        tn = tn.replace(bad, good)
        an = an.replace(bad, good)
    out["track_name"] = tn
    out["artist_name"] = an
    # also keep an accent-stripped variant to help resolver
    out["_track_name_ascii"] = _strip_accents(tn.lower())
    out["_artist_name_ascii"] = _strip_accents(an.lower())
    return out


# Show source path for the Collection model (debug by default; opt-in to INFO via env)
try:
    _src = inspect.getfile(Collection)
    if os.getenv("SHOW_COLLECTIONS_SRC", "").lower() in ("1", "true", "yes", "on"):
        logger.info(f"USING Collection from {_src}")
    else:
        logger.debug(f"USING Collection from {_src}")
except Exception:
    # Avoid any import-time failures just from logging
    logger.debug("Could not determine Collection model source path", exc_info=True)

router = APIRouter(prefix="/collections")


@router.post("/import-json", response_model=ImportResult)
def import_collection(payload: CollectionImportPayload, db: Session = Depends(get_db)):
    try:
        c_in = payload.collection
        skip_resolve = bool(getattr(payload, "skipResolve", getattr(payload, "skip_resolve", False)))

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

        def resolve_for_item(it) -> tuple[int | None, dict | None]:
            """
            Return (track_id, unresolved_dict). Exactly one of them is non-None.
            Uses coerce_row() so the resolver always gets canonical keys.
            """
            # a) direct numeric DB track id
            tid = getattr(it, "trackId", None)
            if tid is not None:
                if db.get(Track, tid):
                    return tid, None
                return None, {"ranking": it.ranking, "reason": "trackId not found", "trackId": tid}

            # b) DB lookup by spotifyTrackId (if present)
            spid = getattr(it, "spotifyTrackId", None)
            if spid:
                found = db.exec(select(Track.id).where(Track.spotify_track_id == spid)).scalar_one_or_none()
                if found:
                    return found, None
                # fall through to metadata resolution

            # c) metadata resolution (normalize incoming fields first)
            #    get a plain dict from the pydantic model
            if hasattr(it, "model_dump"):
                raw = it.model_dump()
            elif hasattr(it, "dict"):
                raw = it.dict()
            else:
                # last resort
                raw = {k: getattr(it, k, None) for k in dir(it) if not k.startswith("_")}

            norm = coerce_row(raw)
            track_name = norm.get("track_name")
            artist_name = norm.get("artist_name")
            year = norm.get("year_released")

            if skip_resolve:
                return None, {
                    "ranking": it.ranking,
                    "title": track_name, "artistName": artist_name, "year": year,
                    "spotifyTrackId": spid, "reason": "skipped resolution"
                }

            # Debug breadcrumb
            logger.debug(f"resolve(meta): rank={it.ranking} | {track_name!r} — {artist_name!r} ({year})")

            try:
                resolved = resolve_track_id_by_meta(db, track_name, artist_name, year)
            except Exception as e:
                logger.warning(f"resolve_track_id_by_meta failed (rank={it.ranking}): {e}", exc_info=True)
                resolved = None

            # Accept int or dict, convert dict -> DB track_id
            track_id = None
            if isinstance(resolved, int):
                track_id = resolved
            elif isinstance(resolved, dict):
                # prefer direct track_id if your resolver provides it
                track_id = resolved.get("track_id")
                if not track_id:
                    spid_res = resolved.get("spotify_track_id") or resolved.get("spotifyTrackId")
                    if spid_res:
                        track_id = db.exec(
                            select(Track.id).where(Track.spotify_track_id == spid_res)
                        ).scalar_one_or_none()

            if track_id:
                return track_id, None

            return None, {
                "ranking": it.ranking,
                "title": track_name, "artistName": artist_name, "year": year,
                "spotifyTrackId": spid, "reason": "no match"
             }

        # ---------- main loop ----------
        for item in payload.tracks:
            track_id, unresolved_rec = resolve_for_item(item)

            # If resolver failed, try creating missing Artist/Track before giving up
            if unresolved_rec is not None:
                if unresolved_rec.get("reason") != "skipped resolution":
                    created_tid = ensure_track_for_meta(
                        db=db,
                        track_name=unresolved_rec.get("title"),
                        artist_name=unresolved_rec.get("artistName"),
                        year=unresolved_rec.get("year"),
                        spotify_track_id=unresolved_rec.get("spotifyTrackId"),
                    )
                    if created_tid:
                        track_id = created_tid
                        unresolved_rec = None

                if unresolved_rec is not None:
                    unresolved.append(unresolved_rec)
                    continue

            # proceed as before
            blurb = getattr(item, "intro", None)

            if item.ranking in existing:
                row = existing[item.ranking]
                changed = False
                if row.track_id != track_id:
                    row.track_id = track_id;
                    changed = True
                if blurb is not None and getattr(row, "intro", None) != blurb:
                    row.intro = blurb;
                    changed = True
                if changed:
                    to_upsert.append(row);
                    updated += 1
            else:
                row = CollectionTrackRanking(
                    collection_id=coll.id, track_id=track_id, ranking=item.ranking
                )
                if blurb:
                    row.intro = blurb
                to_upsert.append(row);
                inserted += 1

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
        logger.exception(f"import-json failed; Collection from {src}")
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


@router.post("/import-json-file/{slug}", response_model=ImportResult)
def import_collection_from_file(slug: str, db: Session = Depends(get_db)):
    """
    Load data/json_files/collections/{slug}.json from project root and import it
    using the same semantics as POST /collections/import-json.

    It prefers the camelCase `tracks` array produced by the generator.
    If missing, it falls back to assembling tracks from `track_ranking` + `track`.
    """
    # Resolve path from project root
    path = Path(cfg.BASE_DIR) / "data" / "json_files" / "collections" / f"{slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Collection JSON not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read JSON file: {e}")

    # Extract collection header
    coll_meta = doc.get("collection") or {}
    coll_name = coll_meta.get("name") or slug.replace("_", " ").title()
    coll_intro = coll_meta.get("intro") if isinstance(coll_meta.get("intro"), str) else None

    # Prefer modern camelCase items
    items = doc.get("tracks")

    # Fallback: reconstruct items from legacy sections
    if not items:
        legacy_tracks = doc.get("track") or []            # snake_case list of tracks
        legacy_ranks  = doc.get("track_ranking") or []    # {rank, spotify_track_id, intro}

        by_spid = {}
        for t in legacy_tracks:
            spid = t.get("spotify_track_id")
            if spid:
                by_spid[spid] = t

        items = []
        for r in legacy_ranks:
            spid = r.get("spotify_track_id")
            meta = by_spid.get(spid, {})
            items.append({
                "ranking": r.get("rank"),
                "spotifyTrackId": spid,
                "title": meta.get("track_name"),
                "artistName": meta.get("artist_name"),
                "year": meta.get("year_released"),
                "intro": r.get("intro"),
            })

    # Filter out malformed entries (need a ranking)
    items = [it for it in (items or []) if it.get("ranking") is not None]
    if not items:
        raise HTTPException(status_code=400, detail="No tracks found to import in JSON file.")

    # Build the payload model (Pydantic will coerce dicts)
    c_in = CollectionIn(name=coll_name, slug=slug, intro=coll_intro)
    payload = CollectionImportPayload(collection=c_in, tracks=items)

    # Reuse the existing importer logic
    return import_collection(payload, db)
