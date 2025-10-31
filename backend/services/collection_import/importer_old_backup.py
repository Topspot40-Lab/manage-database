from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy import delete

import backend.config as cfg
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track
from backend.schemas.collection_schemas import CollectionImportPayload, ImportResult, CollectionIn
from backend.services.track_resolver import resolve_track_id_by_meta, ensure_track_for_meta

from .assembler import assemble_items
from .normalizers import coerce_row, as_int_id, coerce_bool, REPAIR_KEYS as BASE_REPAIR_KEYS

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

# Treat some fields as "protected": never overwrite if a non-empty value already exists
PROTECTED_FILL_ONLY = {"detail"}  # add more later if needed

# Also include the new "source_*" fields in the repairable set
REPAIR_KEYS = set(BASE_REPAIR_KEYS) | {
    "source_type", "source_title", "years_on_air", "source_role", "version_notes"
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) == 0
    return False

def _apply_json_track_meta(t: Track, meta: Dict[str, Any], prefer_json: bool) -> Dict[str, Any]:
    """
    Apply JSON metadata onto an existing Track.
    - Respects PROTECTED_FILL_ONLY (fill-only, never overwrite).
    - Otherwise: overwrite if prefer_json=True, else fill-only.
    """
    changes = {}
    for k in REPAIR_KEYS:
        if k not in meta:
            continue
        incoming = meta[k]
        if k == "is_explicit":
            incoming = coerce_bool(incoming)

        current = getattr(t, k, None)

        # Never clobber protected fields if they already have a non-empty value
        if k in PROTECTED_FILL_ONLY:
            if _is_missing(current) and not _is_missing(incoming):
                setattr(t, k, incoming)
                changes[k] = incoming
            continue  # skip normal logic for protected keys

        # Normal behavior for other fields
        if prefer_json:
            if not _is_missing(incoming) and incoming != current:
                setattr(t, k, incoming)
                changes[k] = incoming
        else:
            if _is_missing(current) and not _is_missing(incoming):
                setattr(t, k, incoming)
                changes[k] = incoming
    return changes

def _pick_first(*vals):
    for v in vals:
        if v is not None and not _is_missing(v):
            return v
    return None

def _augment_meta_with_source_fields(meta: Dict[str, Any] | None, item: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Build a dict that contains canonical source_* fields derived from either the item or meta.
    Mappings:
      show_name   -> source_title
      year_on_air -> years_on_air  (also accept years_on_air as-is)
      show_genre  -> source_role
      source_type -> default to 'TV' when show_* fields are present or genre looks like TV
    """
    meta = dict(meta or {})
    item = item or {}

    # Source title
    source_title = _pick_first(
        item.get("source_title"), meta.get("source_title"),
        item.get("show_name"), meta.get("show_name")
    )
    if source_title:
        meta["source_title"] = source_title

    # Years on air (normalize both spellings to 'years_on_air')
    years_on_air = _pick_first(
        item.get("years_on_air"), meta.get("years_on_air"),
        item.get("year_on_air"), meta.get("year_on_air"),
        item.get("yearOnAir"), meta.get("yearOnAir")
    )
    if years_on_air:
        meta["years_on_air"] = years_on_air

    # Source role (e.g., THEME, OPENING, etc.) — using show_genre as provided
    source_role = _pick_first(
        item.get("source_role"), meta.get("source_role"),
        item.get("show_genre"), meta.get("show_genre")
    )
    if source_role:
        meta["source_role"] = source_role

    # Source type (default to TV if any of the above are present or the genre looks like TV)
    source_type = _pick_first(item.get("source_type"), meta.get("source_type"))
    if not source_type:
        looks_like_tv = bool(
            source_title or years_on_air or source_role
            or str(item.get("genre", "")).lower() in {"tv themes", "tv", "tv-theme", "tv theme"}
        )
        if looks_like_tv:
            source_type = "TV"
    if source_type:
        meta["source_type"] = source_type

    return meta

# ─────────────────────────────────────────────────────────────────────────────
# Importers
# ─────────────────────────────────────────────────────────────────────────────

def import_from_file(
    db: Session,
    slug: str,
    fill_missing_from_json: bool = False,
    prefer_json: bool = False,
) -> ImportResult:
    """
    Import a collection from a JSON file at:
      data/json_files/collections/{slug}.json

    In addition to the normal behavior, the importer now maps TV-theme fields:
      - show_name   -> source_title
      - year_on_air -> years_on_air (also accepts years_on_air)
      - show_genre  -> source_role
      - infers source_type='TV' when any of the above are present (or genre looks like TV Themes)
    """
    path = Path(cfg.BASE_DIR) / "data" / "json_files" / "collections" / f"{slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Collection JSON not found: {path}")

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read JSON file: {e}")

    coll_meta = doc.get("collection") or {}
    coll_name = coll_meta.get("name") or slug.replace("_", " ").title()
    coll_intro = coll_meta.get("intro") if isinstance(coll_meta.get("intro"), str) else None

    # items: list of dicts ready for payload
    # meta_by_spid: per-SID snake_case meta (includes artist_display_name if present in JSON)
    items, meta_by_spid, rank_to_spid, _rank_to_intro = assemble_items(doc)
    if not items:
        raise HTTPException(status_code=400, detail="No tracks found to import in JSON file.")

    # Upsert collection header
    coll = db.exec(select(Collection).where(Collection.slug == slug)).first()
    if not coll:
        coll = Collection(name=coll_name, slug=slug, intro=coll_intro)
        db.add(coll); db.commit(); db.refresh(coll)
    else:
        dirty = False
        if coll.name != coll_name:
            coll.name = coll_name; dirty = True
        if coll_intro is not None and getattr(coll, "intro", None) != coll_intro:
            coll.intro = coll_intro; dirty = True
        if dirty:
            db.add(coll); db.commit(); db.refresh(coll)

    # Bind items to track ids by SID where possible (create if missing)
    for it in items:
        spid = (
            it.get("spotifyTrackId")
            or it.get("spotify_track_id")
            or it.get("spotify_id")
            or it.get("id")
        )
        if not spid:
            continue

        existing_tid = db.exec(
            select(Track.id).where(Track.spotify_track_id == spid)
        ).one_or_none()

        if existing_tid:
            it["trackId"] = existing_tid

            # Backfill artist_display_name on existing track if missing (or prefer_json=True)
            tid_int = as_int_id(existing_tid)
            if tid_int:
                t_db = db.get(Track, tid_int)
                if t_db:
                    meta = meta_by_spid.get(spid, {}) or {}
                    # Add source_* fields into meta snapshot (from item or meta)
                    meta = _augment_meta_with_source_fields(meta, it)

                    # Prefer explicit display name; otherwise fall back to artistName/artist_name
                    disp = _pick_first(
                        it.get("artist_display_name"),
                        it.get("artistDisplayName"),
                        meta.get("artist_display_name"),
                        it.get("artistName"),
                        it.get("artist_name"),
                        meta.get("artist_name"),
                    )
                    if disp and (prefer_json or not getattr(t_db, "artist_display_name", None)):
                        t_db.artist_display_name = disp
                        db.add(t_db)

                    # Also apply the source_* fields (and any other repairable JSON fields)
                    if meta:
                        _apply_json_track_meta(t_db, meta, prefer_json)
                        db.add(t_db)
            continue

        # Create track if not found
        meta = meta_by_spid.get(spid, {}) or {}
        # Make sure we include source_* fields before creation/update
        meta = _augment_meta_with_source_fields(meta, it)

        created_tid = ensure_track_for_meta(
            db=db,
            track_name=_pick_first(it.get("title"), it.get("track_name"), meta.get("track_name"), meta.get("title")),
            artist_name=_pick_first(
                it.get("artistName"), it.get("artist_name"), meta.get("artist_name"), meta.get("artistDisplayName")
            ),
            year=_pick_first(it.get("year"), it.get("year_released"), meta.get("year_released"), meta.get("year")),
            spotify_track_id=spid,
        )
        if created_tid:
            it["trackId"] = created_tid

            # Immediately set artist_display_name and source_* fields on the new track
            t_db = db.get(Track, created_tid)
            if t_db:
                disp = _pick_first(
                    it.get("artist_display_name"),
                    it.get("artistDisplayName"),
                    meta.get("artist_display_name"),
                    it.get("artistName"),
                    it.get("artist_name"),
                    meta.get("artist_name"),
                )
                if disp and (prefer_json or not getattr(t_db, "artist_display_name", None)):
                    t_db.artist_display_name = disp

                # Apply source_* and friends via the same pathway
                _apply_json_track_meta(t_db, meta, prefer_json)
                db.add(t_db)

    # Build payload and reuse core importer
    payload = CollectionImportPayload(
        collection=CollectionIn(name=coll_name, slug=slug, intro=coll_intro),
        tracks=items
    )
    result = import_payload(db, payload)

    # Optional repair pass (applies JSON meta—now including source_*—and respects PROTECTED_FILL_ONLY)
    if fill_missing_from_json:
        try:
            updated = merged = 0
            ctr_rows = db.exec(
                select(CollectionTrackRanking).where(
                    CollectionTrackRanking.collection_id == coll.id
                )
            ).all()

            for ctr_row in ctr_rows:
                t: Optional[Track] = db.get(Track, ctr_row.track_id)
                if not t:
                    continue
                spid_from_db = getattr(t, "spotify_track_id", None)
                spid_from_rank = rank_to_spid.get(ctr_row.ranking)
                desired_spid = spid_from_db or spid_from_rank
                meta = meta_by_spid.get(desired_spid) if desired_spid else None

                # Mix in source_* from the item if we have it (best-effort; not all callers have item handy here)
                # We don't have the original item by rank mapped here, so just augment from meta alone
                meta = _augment_meta_with_source_fields(meta or {}, None)

                incoming_spid = (meta or {}).get("spotify_track_id")

                # merge over to canonical if SID belongs to a different row
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
        except Exception:
            db.rollback()  # be conservative; import already succeeded

    return result

def import_payload(db: Session, payload: CollectionImportPayload) -> ImportResult:
    c_in = payload.collection
    # Upsert collection again (idempotent when called from file path too)
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

    existing = {
        r.ranking: r
        for r in db.exec(
            select(CollectionTrackRanking).where(
                CollectionTrackRanking.collection_id == coll.id
            )
        ).all()
    }

    # pre-validate duplicate ranks
    seen, dup_ranks = set(), []
    for it in payload.tracks:
        if it.ranking in seen:
            dup_ranks.append(it.ranking)
        else:
            seen.add(it.ranking)
    if dup_ranks:
        raise HTTPException(
            status_code=400,
            detail={"message": "Duplicate rankings in payload", "ranks": sorted(set(dup_ranks))}
        )

    inserted = updated = 0
    unresolved: List[dict] = []
    to_upsert: List[CollectionTrackRanking] = []
    incoming_ranks = {it.ranking for it in payload.tracks}

    def resolve_for_item(it) -> tuple[int | None, dict | None]:
        # snapshot dict
        if hasattr(it, "model_dump"):
            raw = it.model_dump()
        elif hasattr(it, "dict"):
            raw = it.dict()
        elif isinstance(it, dict):
            raw = it
        else:
            raw = {k: getattr(it, k, None) for k in dir(it) if not k.startswith("_")}

        tid = as_int_id(raw.get("trackId") or raw.get("track_id"))
        spid = (
            raw.get("spotifyTrackId")
            or raw.get("spotify_track_id")
            or raw.get("spotify_id")
            or raw.get("id")
        )

        if tid is not None:
            if db.get(Track, tid):
                return tid, None
            return None, {"ranking": raw.get("ranking"), "reason": "trackId not found", "trackId": tid}

        if spid:
            found_row = db.exec(select(Track.id).where(Track.spotify_track_id == spid)).first()
            found = as_int_id(found_row)
            if found:
                return found, None

        # fallback: metadata resolution
        norm = coerce_row(raw)
        track_name, artist_name, year = norm.get("track_name"), norm.get("artist_name"), norm.get("year_released")
        try:
            resolved = resolve_track_id_by_meta(db, track_name, artist_name, year)
        except Exception:
            resolved = None

        track_id = None
        if isinstance(resolved, int):
            track_id = resolved
        elif isinstance(resolved, dict):
            track_id = resolved.get("track_id")
            if not track_id:
                spid_res = (resolved.get("spotify_track_id") or resolved.get("spotifyTrackId"))
                if spid_res:
                    track_id = as_int_id(
                        db.exec(select(Track.id).where(Track.spotify_track_id == spid_res)).first()
                    )

        if track_id:
            return track_id, None
        return None, {
            "ranking": raw.get("ranking"),
            "title": track_name, "artistName": artist_name, "year": year,
            "spotifyTrackId": spid, "reason": "no match"
        }

    # main loop
    for item in payload.tracks:
        track_id, unresolved_rec = resolve_for_item(item)

        if unresolved_rec is not None:
            if unresolved_rec.get("reason") != "skipped resolution":
                spid_try = unresolved_rec.get("spotifyTrackId")
                if spid_try:
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

        blurb = getattr(item, "intro", None)

        # attach missing SID if input has one
        try:
            spid_from_input = getattr(item, "spotifyTrackId", None)
            if track_id and spid_from_input:
                t_db = db.get(Track, track_id)
                if t_db and not getattr(t_db, "spotify_track_id", None):
                    conflict_row = db.exec(
                        select(Track.id).where(Track.spotify_track_id == spid_from_input)
                    ).first()
                    conflict = as_int_id(conflict_row)
                    if not conflict or conflict == int(track_id):
                        t_db.spotify_track_id = spid_from_input
                        db.add(t_db)
        except Exception:
            pass

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

    unresolved.sort(key=lambda d: d["ranking"])

    # commit
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
