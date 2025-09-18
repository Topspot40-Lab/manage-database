"""
Single-source logging controls for TopSpot.
Edit LOG_LEVELS_BY_MODULE below to change per-module verbosity.
"""

from __future__ import annotations
import os
from .helpers import env_bool  # used for the toggles below

# ── Global default (root) ────────────────────────────────────────────────
# Set in .env (e.g., LOG_LEVEL=INFO). All modules inherit this unless overridden.
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()

# Optional: show logging configuration summary at startup
# If true: summary prints at INFO. If false: summary prints only at DEBUG.
LOG_SHOW_CONFIG = env_bool("LOG_SHOW_CONFIG", False)



# ── Per-module overrides (this is the ONE place you control modules) ──────
# Keep entries at "INFO" so you can see what exists.
# Flip any line to "DEBUG" when you want it chatty, then restart the app.
LOG_LEVELS_BY_MODULE = {
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
    "track_detail_locales": "INFO",  # legacy/bare logger name if used
    "backend.startup": "WARNING",  # hides INFO, only WARNING+ will show

    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "INFO",
    "backend.logging.track_logging": "INFO",
    "tts_logger": "INFO",            # legacy/bare logger name if used
    "supabase_summary": "INFO",      # legacy/bare logger name if used
    "tts_diagnostics": "INFO",       # legacy/bare logger name if used

    # === DEBUG OVERRIDES (flip these when needed) =========================
    # "backend.meta.log_demo": "DEBUG",
    # "backend.services.db_queries": "DEBUG",
    # "backend.routers.collections_generate": "DEBUG",
    # "backend.routers.collections": "DEBUG",
    # =====================================================================

    # --- Third-party noise control ---------------------------------------
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",

    # Framework noise (tune as needed)
    "uvicorn": "WARNING",
    "uvicorn.error": "WARNING",   # hides startup INFO lines
    "uvicorn.access": "WARNING",  # access logs already reduced; set to "INFO" if you want request lines

}

# ── Optional: file/color output toggles (used by logging_setup.py if wired) ─
LOG_FILE_ENABLED = env_bool("LOG_FILE_ENABLED", True)
LOG_COLOR_ENABLED = env_bool("LOG_COLOR_ENABLED", True)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "backend/logs/topspot.log")
