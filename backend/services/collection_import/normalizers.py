from __future__ import annotations
import unicodedata
from typing import Any, Dict, Optional

# Canonical key mapping for resolver
CANON_KEYS = {
    # title
    "title": "track_name", "track": "track_name", "trackTitle": "track_name",
    "track_title": "track_name", "trackName": "track_name", "track_name": "track_name",
    # artist
    "artist": "artist_name", "artistName": "artist_name", "artist_name": "artist_name",
    "artistDisplayName": "artist_name", "artist_display_name": "artist_name",
    # year
    "year": "year_released", "yearReleased": "year_released", "year_released": "year_released",
}

SMART_APOS = {"\u2019": "'", "\u2018": "'"}

REPAIR_KEYS = [
    "spotify_track_id", "duration_ms", "popularity",
    "album_name", "album_artwork", "year_released", "is_explicit", "detail",
    "artist_display_name",   # backfill nicer display names
    "track_name",            # backfill pretty titles
]

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def coerce_bool(v):
    if isinstance(v, bool) or v is None: return v
    s = str(v).strip().lower()
    if s in ("true", "1", "t", "yes", "y"): return True
    if s in ("false", "0", "f", "no", "n"): return False
    return None

def coerce_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        out[CANON_KEYS.get(k, k)] = v
    tn = (out.get("track_name") or "").strip()
    an = (out.get("artist_name") or "").strip()
    for bad, good in SMART_APOS.items():
        tn = tn.replace(bad, good); an = an.replace(bad, good)
    out["track_name"] = tn
    out["artist_name"] = an
    out["_track_name_ascii"] = strip_accents(tn.lower())
    out["_artist_name_ascii"] = strip_accents(an.lower())
    return out

def normalize_track_item(t: dict) -> dict:
    # --- Promote camelCase → snake/canonical once (keep together) ---
    if "title" in t and "track_name" not in t:
        t["track_name"] = t.get("title")
    if "artistName" in t and "artist_name" not in t:
        t["artist_name"] = t.get("artistName")
    if "albumName" in t and "album_name" not in t:
        t["album_name"] = t.get("albumName")
    if "artistDisplayName" in t and "artist_display_name" not in t:
        t["artist_display_name"] = t.get("artistDisplayName")

    # New duet format → canonical
    if "featured_artist" in t and "featured_artist_name" not in t:
        t["featured_artist_name"] = t.get("featured_artist")
    if "featured_artist_id" in t and "featured_artist_sid" not in t:
        t["featured_artist_sid"] = t.get("featured_artist_id")
    if "featuredArtist" in t and "featured_artist_name" not in t:
        t["featured_artist_name"] = t.get("featuredArtist")
    if "featuredArtistId" in t and "featured_artist_sid" not in t:
        t["featured_artist_sid"] = t.get("featuredArtistId")

    # Common camelCase → snake/canonical (misc fields)
    if "rank" in t and "ranking" not in t:
        t["ranking"] = t.get("rank")
    if "modeFlag" in t and "mode_flag" not in t:
        t["mode_flag"] = t.get("modeFlag")
    if "durationMs" in t and "duration_ms" not in t:
        t["duration_ms"] = t.get("durationMs")
    if "yearReleased" in t and "year" not in t and "year_released" not in t:
        t["year"] = t.get("yearReleased")
    if "isExplicit" in t and "is_explicit" not in t:
        t["is_explicit"] = t.get("isExplicit")
    if "explicit" in t and "is_explicit" not in t:
        t["is_explicit"] = t.get("explicit")
    if "spotifyArtistId" in t and "spotify_artist_id" not in t:
        t["spotify_artist_id"] = t.get("spotifyArtistId")

    # Defaults / fallbacks
    if not t.get("mode_flag"):
        t["mode_flag"] = "SOLO"

    # Album art variants
    if "album_art_url" in t and "album_artwork" not in t:
        t["album_artwork"] = t.get("album_art_url")
    if "albumArtUrl" in t and "album_artwork" not in t:
        t["album_artwork"] = t.get("albumArtUrl")
    if "albumArtwork" in t and "album_artwork" not in t:
        t["album_artwork"] = t.get("albumArtwork")

    # Display-name fallbacks
    if "artist_display_name" not in t and "artist_name" in t:
        t["artist_display_name"] = t.get("artist_name")
    if "track_display_name" not in t and "track_name" in t:
        t["track_display_name"] = t.get("track_name")

    # blanks → None
    for k, v in list(t.items()):
        if isinstance(v, str) and v.strip() == "":
            t[k] = None
    return t

def as_int_id(val) -> Optional[int]:
    if val is None: return None
    if isinstance(val, int): return val
    if hasattr(val, "_mapping"):
        try: return int(next(iter(val._mapping.values())))
        except Exception: return None
    if isinstance(val, (tuple, list)) and val:
        try: return int(val[0])
        except Exception: return None
    return None
