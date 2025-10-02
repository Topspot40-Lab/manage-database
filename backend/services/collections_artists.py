# backend/services/collections_artists.py
from __future__ import annotations
from typing import Any, Dict, List

def _coalesce(*vals: str | None) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _norm(name: str) -> str:
    return (name or "").strip().lower()

def build_artist_table_from_tracks(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    artist_tbl: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for t in tracks:
        # main
        main = _coalesce(t.get("artist_name"))
        if main:
            k = _norm(main)
            if k not in seen:
                seen.add(k)
                artist_tbl.append({
                    "artist_name": main,
                    "spotify_artist_id": (
                        t.get("spotify_artist_id")
                        or t.get("artist_id")  # legacy fallback
                        or None
                    ),
                    "artist_artwork": None,
                    "artist_description": None,
                })

        # featured
        feat = _coalesce(t.get("featured_artist"), t.get("featured_artist_name"))
        if feat:
            kf = _norm(feat)
            if kf not in seen:
                seen.add(kf)
                artist_tbl.append({
                    "artist_name": feat,
                    "spotify_artist_id": (
                        t.get("featured_artist_id")
                        or t.get("featured_artist_sid")  # legacy misname
                        or None
                    ),
                    "artist_artwork": None,
                    "artist_description": None,
                })
    return artist_tbl

def backfill_featured_artist_ids_from_enriched_table(
    artist_tbl: List[Dict[str, Any]],
    tracks: List[Dict[str, Any]],
) -> None:
    name_to_id = {}
    for a in artist_tbl:
        nm = (a.get("artist_name") or "").strip().lower()
        if nm and a.get("spotify_artist_id"):
            name_to_id[nm] = a["spotify_artist_id"]

    for t in tracks:
        feat = (t.get("featured_artist") or t.get("featured_artist_name") or "").strip().lower()
        if feat and not t.get("featured_artist_id"):
            t["featured_artist_id"] = name_to_id.get(feat)
