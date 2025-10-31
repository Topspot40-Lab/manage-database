# backend/services/collection_import/track_binding.py
from __future__ import annotations
from typing import Dict, Any, List
from sqlmodel import Session, select
from backend.models.dbmodels import Track
from backend.services.track_resolver import ensure_track_for_meta
from .meta_utils import _pick_first, _apply_json_track_meta, _augment_meta_with_source_fields


def ensure_tracks_for_items(db: Session, items: List[dict], meta_by_spid: Dict[str, Any], prefer_json: bool) -> None:
    """Ensure all items have a valid track_id, creating tracks as needed."""
    for it in items:
        spid = it.get("spotifyTrackId") or it.get("spotify_track_id")
        if not spid:
            continue

        # Check if this track already exists (by Spotify ID only)
        existing_tid = db.exec(select(Track.id).where(Track.spotify_track_id == spid)).one_or_none()
        if existing_tid:
            it["trackId"] = existing_tid
            t_db = db.get(Track, int(existing_tid))
            meta = meta_by_spid.get(spid, {}) or {}
            meta = _augment_meta_with_source_fields(meta, it)
            disp = _pick_first(
                it.get("artist_display_name"),
                it.get("artistDisplayName"),
                meta.get("artist_display_name"),
                it.get("artistName"),
                it.get("artist_name"),
            )
            if disp and (prefer_json or not getattr(t_db, "artist_display_name", None)):
                t_db.artist_display_name = disp
            _apply_json_track_meta(t_db, meta, prefer_json)
            db.add(t_db)
            continue

        # Create new track
        meta = meta_by_spid.get(spid, {}) or {}
        meta = _augment_meta_with_source_fields(meta, it)

        created_tid = ensure_track_for_meta(
            db=db,
            track_name=_pick_first(it.get("title"), it.get("track_name"), meta.get("track_name")),
            artist_name=_pick_first(it.get("artistName"), it.get("artist_name"), meta.get("artist_name")),
            year=_pick_first(it.get("year"), it.get("year_released"), meta.get("year_released")),
            spotify_track_id=spid,
        )
        if created_tid:
            it["trackId"] = created_tid
            t_db = db.get(Track, created_tid)
            disp = _pick_first(
                it.get("artist_display_name"),
                it.get("artistDisplayName"),
                meta.get("artist_display_name"),
                it.get("artistName"),
                it.get("artist_name"),
            )
            if disp and (prefer_json or not getattr(t_db, "artist_display_name", None)):
                t_db.artist_display_name = disp
            _apply_json_track_meta(t_db, meta, prefer_json)
            db.add(t_db)

    db.commit()
