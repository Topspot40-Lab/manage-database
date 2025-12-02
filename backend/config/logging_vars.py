"""
Single-source logging controls for TopSpot.
Edit LOG_LEVELS_BY_MODULE below to change per-module verbosity.
"""

from __future__ import annotations
import os
from .helpers import env_bool  # used for the toggles below

# ── Global default (root) ────────────────────────────────────────────────
# During development, DEBUG gives full visibility.
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "DEBUG").upper()

# Optional: show logging configuration summary at startup
LOG_SHOW_CONFIG = env_bool("LOG_SHOW_CONFIG", False)


# ── Per-module overrides (this is the ONE place you control modules) ──────
LOG_LEVELS_BY_MODULE = {
    # ----------------------------------------------------------------------
    # CORE PLAYBACK PIPELINE — CRITICAL FOR DIAGNOSTICS
    # ----------------------------------------------------------------------
    "backend.services.spotify.playback": "DEBUG",
    # Everything else quiet:
    "backend.services.radio_runtime": "INFO",
    "backend.services.playback_helpers": "INFO",
    "backend.routers.playback_control": "INFO",
    "backend.state": "INFO",

    "backend.routers.decade_genre_player": "INFO",
    "backend.routers.collections_player": "INFO",

    # --- Your modules (baseline = INFO) -----------------------------------
    "backend.meta.log_demo": "INFO",
    "backend.services.curate": "INFO",
    "backend.services.track_generator": "INFO",
    "backend.services.db_queries": "INFO",
    "backend.services.spotify_service": "INFO",
    "backend.services.xai_api_client": "INFO",
    "backend.services.utils": "INFO",
    "backend.services.supabase_playback": "INFO",

    "backend.routers.collections_generate": "INFO",
    "backend.routers.generate_json": "INFO",
    "backend.routers.insert_json": "INFO",
    "backend.routers.load_json_track_file": "INFO",
    "backend.routers.validate_json": "INFO",
    "backend.routers.supabase_summary": "INFO",
    "backend.routers.supabase_loader": "INFO",
    "backend.routers.tts_intro": "INFO",
    "backend.routers.tts_detail": "INFO",
    "backend.routers.llm_client": "INFO",
    "backend.routers.collections": "INFO",

    "track_detail_locales": "INFO",  # legacy/bare logger names
    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "INFO",
    "backend.logging.track_logging": "INFO",
    "tts_logger": "INFO",
    "supabase_summary": "INFO",
    "tts_diagnostics": "INFO",

    # Startup noise — bump to INFO during dev
    "backend.startup": "INFO",

    # --- Third-party noise control ---------------------------------------
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",

    # Framework noise (tune as needed)
    "uvicorn": "INFO",
    "uvicorn.error": "INFO",    # show startup info
    "uvicorn.access": "INFO",   # show request lines
}


# ── Optional: file/color output toggles (used by logging_setup.py if wired) ─
LOG_FILE_ENABLED = env_bool("LOG_FILE_ENABLED", True)
LOG_COLOR_ENABLED = env_bool("LOG_COLOR_ENABLED", True)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "backend/logs/topspot.log")
