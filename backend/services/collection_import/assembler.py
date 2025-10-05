from __future__ import annotations
from typing import Any, Dict, List, Tuple

from .normalizers import normalize_track_item

def _get_spid(d: Dict[str, Any]):
    return (
        d.get("spotify_track_id")
        or d.get("spotifyTrackId")
        or d.get("spotify_id")
        or d.get("id")
    )

def _get_rank(d: Dict[str, Any]):
    rk = d.get("rank")
    return rk if isinstance(rk, int) else d.get("ranking")

def _merge_field(dst: Dict[str, Any], src: Dict[str, Any], *aliases: str, to: str | None = None):
    """
    If any of 'aliases' exists on src and 'to' (or the same name) not already set on dst,
    copy it over. Example: _merge_field(m, r, "albumName", to="album_name")
    """
    target = to or aliases[0]
    if target in dst and dst[target] is not None:
        return
    for a in aliases:
        if a in src and src[a] is not None:
            dst[target] = src[a]
            return

def build_maps(doc: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[int, str], Dict[int, str]]:
    meta_by_spid: Dict[str, Dict[str, Any]] = {}
    rank_to_spid: Dict[int, str] = {}
    rank_to_intro: Dict[int, str] = {}

    # Legacy full meta: stash normalized rows keyed by spotify_track_id
    for t in doc.get("track") or []:
        spid = _get_spid(t)
        if spid:
            meta_by_spid[spid] = normalize_track_item(dict(t))

    # Legacy ranks (rank + SID + maybe intro)
    for r in doc.get("track_ranking") or []:
        rk, spid = _get_rank(r), _get_spid(r)
        if isinstance(rk, int) and spid:
            rank_to_spid[rk] = spid
            if r.get("intro"):
                rank_to_intro[rk] = r["intro"]

    # Modern ranks (camelCase), also merge useful meta seen only here
    for r in doc.get("trackRanking") or []:
        rk, spid = _get_rank(r), _get_spid(r)
        if not (isinstance(rk, int) and spid):
            continue

        rank_to_spid[rk] = spid
        if r.get("intro"):
            rank_to_intro[rk] = r["intro"]

        m = dict(meta_by_spid.get(spid, {}))
        # album & year
        _merge_field(m, r, "albumName", to="album_name")
        _merge_field(m, r, "albumArtUrl", to="album_artwork")
        _merge_field(m, r, "year", to="year_released")
        # display / ids
        _merge_field(m, r, "artistDisplayName", to="artist_display_name")
        _merge_field(m, r, "spotifyArtistId", to="spotify_artist_id")
        _merge_field(m, r, "trackDisplayName", to="track_display_name")
        # TV theme extras (both snake and camel just in case)
        _merge_field(m, r, "show_name")
        _merge_field(m, r, "years_on_air")
        _merge_field(m, r, "show_genre")
        # keep it
        if m:
            meta_by_spid[spid] = m

    return meta_by_spid, rank_to_spid, rank_to_intro

def _mostly_missing_sids(arr: List[Dict[str, Any]]) -> bool:
    if not arr:
        return False
    missing = sum(1 for it in arr if not (it.get("spotifyTrackId") or it.get("spotify_track_id")))
    return missing >= max(1, int(0.8 * len(arr)))

def assemble_items(doc: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[int, str], Dict[int, str]]:
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
            if not isinstance(rk, int):
                continue
            spid = rank_to_spid.get(rk)
            meta = meta_by_spid.get(spid, {}) if spid else {}
            album_art = (meta.get("album_artwork") or meta.get("albumArtwork") or r.get("albumArtUrl"))
            row = {
                "ranking": rk,
                "spotifyTrackId": spid,
                "title": (meta.get("track_name") or meta.get("title") or r.get("title")),
                "artistName": (meta.get("artist_name") or meta.get("artistName") or r.get("artistName")),
                "year": (meta.get("year_released") or meta.get("year") or r.get("year")),
                "intro": r.get("intro"),
                "albumName": (meta.get("album_name") or r.get("albumName")),
                "albumArtwork": album_art,
            }
            # carry TV theme extras/display if present
            for k in ("show_name", "years_on_air", "show_genre", "track_display_name", "artist_display_name", "spotify_artist_id"):
                if meta.get(k) is not None:
                    row[k] = meta[k]
            rebuilt.append(row)
        items = rebuilt

    # Normalize + backfill per-row
    items = [normalize_track_item(dict(it)) for it in (items or [])]

    # Backfill missing spotifyTrackId from rank_to_spid on a per-item basis
    for it in items:
        rk = _get_rank(it)
        if not it.get("spotifyTrackId") and not it.get("spotify_track_id") and isinstance(rk, int):
            spid = rank_to_spid.get(rk)
            if spid:
                it["spotifyTrackId"] = spid

    normed: List[Dict[str, Any]] = []
    for it in items:
        rk = _get_rank(it)
        if rk is None:
            continue
        it["ranking"] = int(rk)

        spid = _get_spid(it)
        meta = meta_by_spid.get(spid) if spid else None
        if meta:
            # Basic fields
            it.setdefault("title", meta.get("track_name") or meta.get("title"))
            it.setdefault("artistName", meta.get("artist_name") or meta.get("artistDisplayName"))
            it.setdefault("year", meta.get("year_released") or meta.get("year"))
            # Album art/name
            if "albumArtwork" not in it and meta.get("album_artwork"):
                it["albumArtwork"] = meta["album_artwork"]
            it.setdefault("albumName", meta.get("album_name"))
            # TV theme extras / display / ids
            it.setdefault("track_display_name", meta.get("track_display_name"))
            it.setdefault("artist_display_name", meta.get("artist_display_name"))
            it.setdefault("spotify_artist_id", meta.get("spotify_artist_id"))
            it.setdefault("show_name", meta.get("show_name"))
            it.setdefault("years_on_air", meta.get("years_on_air"))
            it.setdefault("show_genre", meta.get("show_genre"))
            # pass along other useful meta for repair phase
            it.setdefault("durationMs", meta.get("duration_ms"))
            it.setdefault("popularity", meta.get("popularity"))
            it.setdefault("isExplicit", meta.get("is_explicit"))
            it.setdefault("detail", meta.get("detail"))

        if not it.get("intro"):
            maybe = _rank_to_intro.get(it["ranking"])
            if maybe:
                it["intro"] = maybe

        normed.append(it)

    return normed, meta_by_spid, rank_to_spid, _rank_to_intro
