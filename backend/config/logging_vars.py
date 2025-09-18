"""
Single-source logging controls for TopSpot.
Edit LOG_LEVELS_BY_MODULE below to change per-module verbosity.
"""

from __future__ import annotations
import os
from .helpers import env_bool  # keep if your logging_setup uses these toggles

# ── Global default (root) ────────────────────────────────────────────────
# Set in .env (e.g., LOG_LEVEL=INFO). All modules inherit this unless overridden.
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()

# ── Per-module overrides (this is the ONE place you control modules) ──────
# Set "DEBUG" for chatty logging; leave "INFO" (or omit) to keep them quieter.
LOG_LEVELS_BY_MODULE = {
    # --- Your modules ---
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
    "track_detail_locales": "INFO",

    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "INFO",
    "backend.logging.track_logging": "INFO",
    "tts_logger": "INFO",
    "supabase_summary": "INFO",
    "tts_diagnostics": "INFO",

    # --- Third-party noise control ---
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",
}

# ── Optional: file/color output toggles (used by logging_setup.py if wired) ─
LOG_FILE_ENABLED = env_bool("LOG_FILE_ENABLED", True)
LOG_COLOR_ENABLED = env_bool("LOG_COLOR_ENABLED", True)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "backend/logs/topspot.log")
