import os
from .helpers import env_bool
# Root/base level
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()

LOG_SUMMARY_ENABLED = env_bool("LOG_SUMMARY_ENABLED", False)

# Steps (kept as-is)
STEP_LOG_LEVELS = {
    "STEP_1":"INFO","STEP_1.A":"INFO","STEP_1.B":"INFO","STEP_1.C":"INFO",
    "STEP_3":"INFO","STEP_3.A":"INFO","STEP_3.B":"INFO",
    "STEP_4":"INFO","STEP_4.A":"INFO","STEP_4.B":"INFO","STEP_4.C":"INFO","STEP_4.D":"INFO","STEP_4.E":"INFO",
    "STEP_5":"INFO","STEP_6":"INFO","STEP_7":"INFO","STEP_8":"INFO",
    "STEP_9":"INFO","STEP_9.A":"INFO","STEP_9.B":"INFO","STEP_9.C":"INFO",
    "STEP_10":"INFO","STEP_11":"INFO",
}

DB_QUERIES_LOG_LEVEL = os.getenv("DB_QUERIES_LOG_LEVEL", "DEBUG").upper()
LOG_LEVEL_COLLECTIONS_GENERATE = (os.getenv("LOG_LEVEL_COLLECTIONS_GENERATE") or LOG_LEVEL).upper()

# Comma-separated extra loggers to force DEBUG
DEBUG_LOGGERS = [s.strip() for s in (os.getenv("DEBUG_LOGGERS") or "").split(",") if s.strip()]

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

    # New: collections generator env-driven level
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
}

LOG_FILE_ENABLED = (os.getenv("LOG_FILE_ENABLED") or "1") not in ("0","false","no","off")
LOG_COLOR_ENABLED = (os.getenv("LOG_COLOR_ENABLED") or "1") not in ("0","false","no","off")
LOG_FILE_PATH = "backend/logs/topspot.log"
