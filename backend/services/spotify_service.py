# backend/services/spotify_service.py
# add at top with the other typing imports
from typing import Mapping, Sequence

"""
spotify_service.py — Unified import layer for Spotify-related services.

This file re-exports functions from the modular `spotify/` package so they
can be imported from a single location elsewhere in the app.

Example:
    from backend.services import spotify_service as spotify
    spotify.get_spotify_client()
"""

__all__ = [
    "get_spotify_client",
    "get_similar_tracks",
    "auto_select_best_spotify_match",
    "enrich_track_from_spotify",
    "enrich_track_simple",            # ← adapter with a stable (title, artist, year) signature
    "safe_slug",
    "clean_track_title",
    "format_artist_display_name",
    "ModeFlag",
    "handle_missing_track",
    "reassign_ranks",
    "log_missing_track_action",
    "prompt_user_for_replacement",
    "choose_spare_track",
]

# ─────────────────────────────────────────────────────────────────────────────
# 🔐 Auth
# ─────────────────────────────────────────────────────────────────────────────
from backend.services.spotify.auth import get_spotify_client

# ─────────────────────────────────────────────────────────────────────────────
# 🔍 Search
# ─────────────────────────────────────────────────────────────────────────────
from backend.services.spotify.search import (
    get_similar_tracks,
    auto_select_best_spotify_match,
)

# ─────────────────────────────────────────────────────────────────────────────
# 🎨 Enrichment (internal)
# ─────────────────────────────────────────────────────────────────────────────
from backend.services.spotify.enrich import enrich_track_from_spotify

# ─────────────────────────────────────────────────────────────────────────────
# 🧹 Helpers
# ─────────────────────────────────────────────────────────────────────────────
from backend.services.spotify.helpers import (
    safe_slug,
    clean_track_title,
    format_artist_display_name,
    ModeFlag,
)

# ─────────────────────────────────────────────────────────────────────────────
# 🩹 Fallbacks + Logging
# ─────────────────────────────────────────────────────────────────────────────
from backend.services.spotify.missing_log import (
    handle_missing_track,
    reassign_ranks,
    log_missing_track_action,
)

# ─────────────────────────────────────────────────────────────────────────────
# 🖐️ CLI Prompts (optional/manual use)
# ─────────────────────────────────────────────────────────────────────────────
from backend.services.spotify.cli_fallbacks import (
    prompt_user_for_replacement,
    choose_spare_track,
)

# ─────────────────────────────────────────────────────────────────────────────
# 🧩 Simple, stable adapter for routers/CLI
# ─────────────────────────────────────────────────────────────────────────────
from typing import Optional, Dict, Any, List
import inspect

# replace the previous _normalize_enriched and enrich_track_simple with these:

def _to_dict(raw: Any) -> Dict[str, Any]:
    """Best-effort: convert various shapes to a dict we can read from."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and raw:
        head = raw[0]
        if isinstance(head, Mapping):
            return dict(head)
    return {}

def _normalize_enriched(raw: Any, *, title: str, artist: str, year: Optional[int]) -> Dict[str, Any]:
    data = _to_dict(raw)

    album = data.get("album")
    album_map: Dict[str, Any] = {}
    if isinstance(album, Mapping):
        album_map = dict(album)

    images = album_map.get("images")
    images_list: List[Dict[str, Any]] = images if isinstance(images, list) else []
    first_image = images_list[0]["url"] if images_list and isinstance(images_list[0], Mapping) and "url" in images_list[0] else None

    return {
        "title": data.get("title") or data.get("name") or title,
        "artist": (
            data.get("artist")
            or data.get("artist_name")
            or (
                ", ".join(a["name"] for a in data.get("artists", []) if isinstance(a, Mapping) and "name" in a)
                if isinstance(data.get("artists"), list) else None
            )
            or artist
        ),
        "year": (
            data.get("year")
            or ((album_map.get("release_date") or "")[:4] if album_map.get("release_date") else None)
            or year
        ),
        "spotify_track_id": data.get("spotify_track_id") or data.get("id"),
        "album_name": data.get("album_name") or album_map.get("name"),
        "album_art_url": data.get("album_art_url") or first_image,
    }

def enrich_track_simple(*, title: str, artist: str, year: Optional[int] = None) -> Dict[str, Any]:
    """
    Stable adapter: always call this with (title, artist, year).
    Adapts to enrich_track_from_spotify's real signature and normalizes output.
    """
    # Try to map our kwargs to whatever the internal function expects.
    try:
        sig = inspect.signature(enrich_track_from_spotify)  # type: ignore
        params = set(sig.parameters.keys())
        kw: Dict[str, Any] = {}
        if "title" in params: kw["title"] = title
        elif "track_title" in params: kw["track_title"] = title
        elif "name" in params: kw["name"] = title

        if "artist" in params: kw["artist"] = artist
        elif "artist_name" in params: kw["artist_name"] = artist

        if "year" in params: kw["year"] = year
        elif "release_year" in params: kw["release_year"] = year

        out = enrich_track_from_spotify(**kw)  # type: ignore
        return _normalize_enriched(out, title=title, artist=artist, year=year)
    except Exception:
        pass

    # Fallback to search helpers
    try:
        client = get_spotify_client()
        sims = get_similar_tracks(client, title=title, artist=artist, year=year)  # type: ignore
        best = auto_select_best_spotify_match(sims, title=title, artist=artist, year=year)  # type: ignore
        return _normalize_enriched(best, title=title, artist=artist, year=year)
    except Exception:
        # Last-resort minimal payload
        return {
            "title": title,
            "artist": artist,
            "year": year,
            "spotify_track_id": None,
            "album_name": None,
            "album_art_url": None,
        }
