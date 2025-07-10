# backend/services/spotify_service.py

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
# 🎨 Enrichment
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
