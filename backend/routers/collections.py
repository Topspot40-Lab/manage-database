# backend/routers/collections.py
from __future__ import annotations

import json
from pathlib import Path
import backend.config as cfg

import os
import inspect
import logging
import unicodedata
from typing import List, Any, Dict, Optional

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
from backend.services.track_resolver import (
    resolve_track_id_by_meta,
    ensure_track_for_meta,
)

# Use namespaced logger so it respects LOG_LEVELS_BY_MODULE["backend.routers.collections"]
logger = logging.getLogger(__name__)

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

# Which track fields we’re willing to repair from JSON
REPAIR_KEYS = [
    "spotify_track_id", "duration_ms", "popularity",
    "album_name", "album_artwork", "year_released", "is_explicit", "detail"
]

def _coerce_bool(v):
    if isinstance(v, bool) or v is None:
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "t", "yes", "y"):
        return True
    if s in ("false", "0", "f", "no", "n"):
        return False
    return None

def _apply_json_track_meta(t: Track, meta: Dict[str, Any], prefer_json: bool) -> Dict[str, Any]:
    """Fill Track columns from meta; return dict of changes applied."""
    changes = {}
    for k in REPAIR_KEYS:
        if k not in meta:
            continue
        incoming = meta[k]
        if k == "is_explicit":
            incoming = _coerce_bool(incoming)
        current = getattr(t, k, None)
        if prefer_json:
            if incoming is not None and incoming != current:
                setattr(t, k, incoming)
                changes[k] = incoming
        else:
            # fill-missing-only
            if (current is None or current == "") and incoming is not None:
                setattr(t, k, incoming)
                changes[k] = incoming
    return changes

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

            # If resolver failed, only create a Track when a spotifyTrackId is present.
            if unresolved_rec is not None:
                if unresolved_rec.get("reason") != "skipped resolution":
                    spid_try = unresolved_rec.get("spotifyTrackId")
                    if spid_try:  # ← guard: never create without a SID
                        created_tid = ensure_track_for_meta(
                            db=db,
                            track_name=unresolved_rec.get("title"),
                            artist_name=unresolved_rec.get("artistName"),
                            year=unresolved_rec.get("year"),
                            spotify_track_id=spid_try,
                        )
                        if created_tid:
                            track_id = created_tid
                            unresolved_rec = None

                if unresolved_rec is not None:
                    unresolved.append(unresolved_rec)
                    continue

            # proceed as before
            blurb = getattr(item, "intro", None)

            # If we matched/created a Track but it has no SID while the input has one,
            # attach the SID now (as long as no other row already owns it).
            try:
                spid_from_input = getattr(item, "spotifyTrackId", None)
                if track_id and spid_from_input:
                    t_db = db.get(Track, track_id)
                    if t_db and not getattr(t_db, "spotify_track_id", None):
                        conflict = db.exec(
                            select(Track.id).where(Track.spotify_track_id == spid_from_input)
                        ).scalar_one_or_none()
                        if not conflict or conflict == track_id:
                            t_db.spotify_track_id = spid_from_input
                            db.add(t_db)  # will flush with the rest
            except Exception:
                logger.debug("sid backfill skipped", exc_info=True)

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
                row = CollectionTrackRanking(
                    collection_id=coll.id, track_id=track_id, ranking=item.ranking
                )
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
def import_collection_from_file(
    slug: str,
    fill_missing_from_json: bool = False,   # NEW
    prefer_json: bool = False,              # NEW
    db: Session = Depends(get_db),
):
    """
    Load data/json_files/collections/{slug}.json from project root and import it
    using the same semantics as POST /collections/import-json.

    It prefers the camelCase `tracks` array produced by the generator.
    If missing, it falls back to assembling tracks from ranking blocks + meta.

    When fill_missing_from_json=true, it will do a repair pass for Track fields
    using metadata present in the JSON (modern or legacy).
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

    # ---- Build metadata maps for the repair/backfill pass ----
    meta_by_spid: Dict[str, Dict[str, Any]] = {}
    rank_to_spid: Dict[int, str] = {}

    def _get_spid(d: Dict[str, Any]):
        return (d.get("spotify_track_id")
                or d.get("spotifyTrackId")
                or d.get("spotify_id")
                or d.get("id"))

    def _get_rank(d: Dict[str, Any]):
        # tolerate both legacy 'rank' and modern 'ranking'
        rk = d.get("rank")
        return rk if isinstance(rk, int) else d.get("ranking")

    # Legacy full meta: doc["track"] (snake_case)
    legacy_tracks = doc.get("track") or []
    for t in legacy_tracks:
        spid = _get_spid(t)
        if spid:
            meta_by_spid[spid] = t

    # Legacy ranking list: doc["track_ranking"] (rank + spotify ID)
    legacy_ranks = doc.get("track_ranking") or []
    for r in legacy_ranks:
        rk = _get_rank(r)
        spid = _get_spid(r)
        if isinstance(rk, int) and spid:
            rank_to_spid[rk] = spid

    # Modern ranking list (camelCase): doc["trackRanking"]
    modern_ranks = doc.get("trackRanking") or []
    for r in modern_ranks:
        rk = _get_rank(r)
        spid = _get_spid(r)
        if isinstance(rk, int) and spid:
            rank_to_spid[rk] = spid
            # stash minimal meta seen only in ranking rows (useful for fallback build)
            m = dict(meta_by_spid.get(spid, {}))
            if "albumName" in r and "album_name" not in m: m["album_name"] = r["albumName"]
            if "albumArtUrl" in r and "album_artwork" not in m: m["album_artwork"] = r["albumArtUrl"]
            if "year" in r and "year_released" not in m: m["year_released"] = r["year"]
            if m:
                meta_by_spid[spid] = m

    # Modern items: capture ranking + extra camelCase meta;
    # also backfill missing spotifyTrackId from rank_to_spid
    if items:
        for it in items:
            rk = _get_rank(it)
            spid = it.get("spotifyTrackId") or it.get("spotify_track_id")
            if not spid and isinstance(rk, int):
                spid = rank_to_spid.get(rk)
                if spid:
                    it["spotifyTrackId"] = spid  # backfill

            if isinstance(rk, int) and spid:
                # Merge modern fields into meta map (normalize camelCase → snake_case)
                m = dict(meta_by_spid.get(spid, {}))
                if "albumName" in it and "album_name" not in m: m["album_name"] = it["albumName"]
                if "albumArtwork" in it and "album_artwork" not in m: m["album_artwork"] = it["albumArtwork"]
                if "durationMs" in it and "duration_ms" not in m: m["duration_ms"] = it["durationMs"]
                if "year" in it and "year_released" not in m: m["year_released"] = it["year"]
                if "detail" in it: m["detail"] = it["detail"]
                if "popularity" in it: m["popularity"] = it["popularity"]
                if "isExplicit" in it and "is_explicit" not in m: m["is_explicit"] = it["isExplicit"]
                if "explicit" in it and "is_explicit" not in m: m["is_explicit"] = it["explicit"]
                if "spotifyTrackId" in it and "spotify_track_id" not in m: m["spotify_track_id"] = it["spotifyTrackId"]
                if m:
                    meta_by_spid[spid] = m

    # Fallback: reconstruct items when modern "tracks" missing
    if not items:
        items = []
        by_spid = meta_by_spid
        # Use whichever ranking block(s) we found
        all_ranks = legacy_ranks or modern_ranks
        for r in all_ranks:
            rk = _get_rank(r)
            if not isinstance(rk, int):
                continue
            spid = rank_to_spid.get(rk)
            meta = by_spid.get(spid, {}) if spid else {}
            # album art may be under 'albumArtUrl' in modern ranking
            album_art = (meta.get("album_artwork") or meta.get("albumArtwork") or r.get("albumArtUrl"))
            items.append({
                "ranking": rk,
                "spotifyTrackId": spid,
                "title": (meta.get("track_name") or meta.get("title") or r.get("title")),
                "artistName": (meta.get("artist_name") or meta.get("artistName") or r.get("artistName")),
                "year": (meta.get("year_released") or meta.get("year") or r.get("year")),
                "intro": r.get("intro"),
                # keep any extra camelCase the generator provided:
                "albumName": (meta.get("album_name") or r.get("albumName")),
                "albumArtwork": album_art,
            })

    # Filter out malformed entries (need a ranking)
    items = [it for it in (items or []) if it.get("ranking") is not None]
    if not items:
        raise HTTPException(status_code=400, detail="No tracks found to import in JSON file.")

    # Build the payload model (Pydantic will coerce dicts)
    c_in = CollectionIn(name=coll_name, slug=slug, intro=coll_intro)
    payload = CollectionImportPayload(collection=c_in, tracks=items)

    # Reuse the existing importer logic (creates/updates ranks; may create tracks)
    result = import_collection(payload, db)

    # ----- Optional repair pass for Track fields from JSON -----
    if fill_missing_from_json:
        try:
            coll = db.exec(select(Collection).where(Collection.slug == slug)).first()
            if coll:
                updated = merged = 0
                with db.no_autoflush:
                    ctr_rows = db.exec(
                        select(CollectionTrackRanking)
                        .where(CollectionTrackRanking.collection_id == coll.id)
                    ).all()

                    for ctr_row in ctr_rows:
                        t: Optional[Track] = db.get(Track, ctr_row.track_id)
                        if not t:
                            continue

                        spid_from_db = getattr(t, "spotify_track_id", None)
                        spid_from_rank = rank_to_spid.get(ctr_row.ranking)
                        desired_spid = spid_from_db or spid_from_rank

                        meta = meta_by_spid.get(desired_spid) if desired_spid else None
                        incoming_spid = (meta or {}).get("spotify_track_id")

                        if incoming_spid and incoming_spid != spid_from_db:
                            owner_id = db.exec(
                                select(Track.id).where(Track.spotify_track_id == incoming_spid)
                            ).first()
                            if owner_id and owner_id != t.id:
                                canonical = db.get(Track, owner_id)
                                _apply_json_track_meta(canonical, meta, prefer_json)
                                db.add(canonical)
                                ctr_row.track_id = canonical.id
                                db.add(ctr_row)
                                merged += 1
                                continue

                        if meta:
                            changes = _apply_json_track_meta(t, meta, prefer_json)
                            if changes:
                                db.add(t)
                                updated += 1

                if updated or merged:
                    db.commit()
                    logger.info(
                        "Repaired %d tracks; merged %d duplicates (prefer_json=%s)",
                        updated, merged, prefer_json
                    )
        except Exception as e:
            logger.warning("Repair-from-JSON pass failed: %s", e, exc_info=True)

    return result
