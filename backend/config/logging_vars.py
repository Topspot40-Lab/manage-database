"""
Env-driven logging variables for TopSpot.
Used by backend/logging_setup.py to build the dictConfig.
"""

import os
from .helpers import env_bool

# Root/base level
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()

# Summary toggle
LOG_SUMMARY_ENABLED = env_bool("LOG_SUMMARY_ENABLED", False)

# ── Ads-specific controls ───────────────────────────────────────────────
LOG_LEVEL_ADS = (os.getenv("LOG_LEVEL_ADS") or LOG_LEVEL).upper()
ADS_LOG_FILE_ENABLED = env_bool("ADS_LOG_FILE_ENABLED", False)
ADS_LOG_FILE_PATH = os.getenv("ADS_LOG_FILE_PATH", "backend/logs/ads.log")

# ── Step loggers (mostly silenced) ───────────────────────────────────────
STEP_LOG_LEVELS = {
    "STEP_1": "INFO", "STEP_1.A": "INFO", "STEP_1.B": "INFO", "STEP_1.C": "INFO",
    "STEP_3": "INFO", "STEP_3.A": "INFO", "STEP_3.B": "INFO",
    "STEP_4": "INFO", "STEP_4.A": "INFO", "STEP_4.B": "INFO", "STEP_4.C": "INFO",
    "STEP_4.D": "INFO", "STEP_4.E": "INFO",
    "STEP_5": "INFO", "STEP_6": "INFO", "STEP_7": "INFO", "STEP_8": "INFO",
    "STEP_9": "INFO", "STEP_9.A": "INFO", "STEP_9.B": "INFO", "STEP_9.C": "INFO",
    "STEP_10": "INFO", "STEP_11": "INFO",
}

# DB / collections levels
DB_QUERIES_LOG_LEVEL = (os.getenv("DB_QUERIES_LOG_LEVEL") or "DEBUG").upper()
LOG_LEVEL_COLLECTIONS_GENERATE = (os.getenv("LOG_LEVEL_COLLECTIONS_GENERATE") or LOG_LEVEL).upper()

# Comma-separated extra loggers to force DEBUG
DEBUG_LOGGERS = [
    s.strip()
    for s in (os.getenv("DEBUG_LOGGERS") or "").split(",")
    if s.strip()
]

# ── Module-specific overrides ────────────────────────────────────────────
LOG_LEVELS_BY_MODULE = {
    # Core services
    "backend.services.spotify_service": "INFO",
    "backend.services.track_generator": "INFO",
    "backend.services.utils": "INFO",
    "backend.services.xai_service": "INFO",
    "backend.services.xai_api_client": "INFO",
    "backend.services.supabase_playback": "INFO",

    # Routers
    "backend.routers.generate_json": "INFO",
    "backend.routers.insert_json": "INFO",
    "backend.routers.load_json_track_file": "INFO",
    "backend.routers.validate_json": "INFO",
    "backend.routers.supabase_summary": "INFO",
    "backend.routers.tts_intro": "INFO",
    "backend.routers.tts_detail": "INFO",
    "track_detail_locales": "INFO",
    "backend.routers.supabase_loader": "INFO",
    "backend.routers.insert_specialty": "INFO",
    "backend.routers.generate_poprock": "INFO",
    "backend.routers.llm_client": "INFO",

    # New: collections generator (env-driven level)
    "backend.routers.collections_generate": LOG_LEVEL_COLLECTIONS_GENERATE,

    # Services (env-driven)
    "backend.services.db_queries": DB_QUERIES_LOG_LEVEL,

    # Utilities / custom
    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "INFO",
    "backend.logging.track_logging": "INFO",
    "tts_logger": "INFO",
    "supabase_summary": "INFO",
    "tts_diagnostics": "INFO",

    # Third-party
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",

    # Ads modules use env-driven level
    "backend.routers.ads_scripts": LOG_LEVEL_ADS,
    "backend.services.ads.script_generator": LOG_LEVEL_ADS,
    "ads_scripts": LOG_LEVEL_ADS,  # fallback bare name
    "backend.services.ads.ad_audio": LOG_LEVEL_ADS,
}

# Global file + color toggles
LOG_FILE_ENABLED = env_bool("LOG_FILE_ENABLED", True)
LOG_COLOR_ENABLED = env_bool("LOG_COLOR_ENABLED", True)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "backend/logs/topspot.log")
