from __future__ import annotations
from typing import Any, Dict, List, Tuple

from .normalizers import normalize_track_item

def _get_spid(d: Dict[str, Any]):
    return (d.get("spotify_track_id") or d.get("spotifyTrackId")
            or d.get("spotify_id") or d.get("id"))

def _get_rank(d: Dict[str, Any]):
    rk = d.get("rank")
    return rk if isinstance(rk, int) else d.get("ranking")

def build_maps(doc: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, str], Dict[int, str]]:
    meta_by_spid: Dict[str, Dict[str, Any]] = {}
    rank_to_spid: Dict[int, str] = {}
    rank_to_intro: Dict[int, str] = {}

    # Legacy full meta
    for t in doc.get("track") or []:
        spid = _get_spid(t)
        if spid:
            meta_by_spid[spid] = t

    # Legacy ranks
    for r in doc.get("track_ranking") or []:
        rk, spid = _get_rank(r), _get_spid(r)
        if isinstance(rk, int) and spid:
            rank_to_spid[rk] = spid
            if r.get("intro"): rank_to_intro[rk] = r["intro"]

    # Modern ranks
    for r in doc.get("trackRanking") or []:
        rk, spid = _get_rank(r), _get_spid(r)
        if isinstance(rk, int) and spid:
            rank_to_spid[rk] = spid
            if r.get("intro"): rank_to_intro[rk] = r["intro"]
            m = dict(meta_by_spid.get(spid, {}))
            if "albumName" in r and "album_name" not in m: m["album_name"] = r["albumName"]
            if "albumArtUrl" in r and "album_artwork" not in m: m["album_artwork"] = r["albumArtUrl"]
            if "year" in r and "year_released" not in m: m["year_released"] = r["year"]
            if m: meta_by_spid[spid] = m

    return meta_by_spid, rank_to_spid, rank_to_intro

def _mostly_missing_sids(arr: List[Dict[str, Any]]) -> bool:
    if not arr: return False
    missing = sum(1 for it in arr if not (it.get("spotifyTrackId") or it.get("spotify_track_id")))
    return missing >= max(1, int(0.8 * len(arr)))

def assemble_items(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Prefer modern tracks array
    items = doc.get("tracks")
    legacy_ranks = doc.get("track_ranking") or []
    modern_ranks = doc.get("trackRanking") or []

    meta_by_spid, rank_to_spid, _rank_to_intro = build_maps(doc)

    # If modern items mostly lack SIDs, rebuild from rank blocks
    if items and _mostly_missing_sids(items) and rank_to_spid:
        rebuilt = []
        ranks_src = modern_ranks or legacy_ranks
        for r in ranks_src:
            rk = _get_rank(r)
            if not isinstance(rk, int): continue
            spid = rank_to_spid.get(rk)
            meta = meta_by_spid.get(spid, {}) if spid else {}
            album_art = (meta.get("album_artwork") or meta.get("albumArtwork") or r.get("albumArtUrl"))
            rebuilt.append({
                "ranking": rk,
                "spotifyTrackId": spid,
                "title": (meta.get("track_name") or meta.get("title") or r.get("title")),
                "artistName": (meta.get("artist_name") or meta.get("artistName") or r.get("artistName")),
                "year": (meta.get("year_released") or meta.get("year") or r.get("year")),
                "intro": r.get("intro"),
                "albumName": (meta.get("album_name") or r.get("albumName")),
                "albumArtwork": album_art,
            })
        items = rebuilt

    # Normalize + backfill per-row
    items = [normalize_track_item(dict(it)) for it in (items or [])]
    normed: List[Dict[str, Any]] = []
    for it in items:
        rk = _get_rank(it)
        if rk is None: continue
        it["ranking"] = int(rk)

        spid = _get_spid(it)
        meta = meta_by_spid.get(spid) if spid else None
        if meta:
            it.setdefault("title", meta.get("track_name") or meta.get("title"))
            it.setdefault("artistName", meta.get("artist_name") or meta.get("artistDisplayName"))
            it.setdefault("year", meta.get("year_released") or meta.get("year"))
            if "albumArtwork" not in it and meta.get("album_artwork"):
                it["albumArtwork"] = meta["album_artwork"]
        if not it.get("intro"):
            maybe = _rank_to_intro.get(it["ranking"])
            if maybe: it["intro"] = maybe

        normed.append(it)

    return normed, meta_by_spid, rank_to_spid, _rank_to_intro
