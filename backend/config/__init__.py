# backend/config/__init__.py
from dotenv import load_dotenv
load_dotenv()  # ensure .env is loaded once when the config package is imported

# Re-export everything so existing `from backend import config` keeps working.

# Helpers
from .helpers import env_bool, env_int, env_list, clamp, extract_spotify_track_id

# App + paths
from .app import APP_VERSION, LAST_UPDATED
from .paths import BASE_DIR, TEST_JSON_DIR, SCHEMA_PATH

# Providers / services
from .spotify import (
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SPOTIFY_MARKET,
    spotify_creds_ok,
)
from .xai import (
    LLM_PROVIDER, XAI_API_KEY, XAI_API_BASE, XAI_API_URL,
    DEFAULT_XAI_MODEL, XAI_MODEL, TEMPERATURE_DEFAULT,
    XAI_CONNECT_TIMEOUT, XAI_READ_TIMEOUT, XAI_MAX_RETRIES, XAI_BACKOFF_FACTOR, XAI_TIMEOUT_SECONDS,
    FALLBACK_TO_TEST_ON_XAI_ERROR, FALLBACK_TEST_FILE_NUMBER, get_active_llm_info,
)
from .supabase import (
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
    LANGUAGE_BUCKETS, BUCKETS, AUDIO_PREFIXES,
    BUCKET_TRACK_INTRO, BUCKET_TRACK_DETAIL, BUCKET_ARTIST, BUCKET_SPOTIFY_TRACK,
    SUPABASE_BUCKET_ARTIST_MP3,
)
from .tts import (
    ELEVENLABS_ENABLE, ELEVENLABS_API_KEY,
    VOICE_ID_INTRO, VOICE_ID_ARTIST, VOICE_ID_TRACK,
    VOICE_STABILITY, VOICE_SIMILARITY,
    ELEVENLABS_MODEL, ELEVEN_MODEL_ID,
    ELEVEN_MODEL_ID_ES, ELEVEN_MODEL_ID_PT_BR,
    ELEVEN_MODELS_SUPPORT_LANGUAGE, ELEVEN_LANGUAGE_CODE_MAP,
    MODEL_BY_LANG, SUPPORTED_LANGS, DEFAULT_LANGUAGE, DEFAULT_TTS_LANGUAGE,
    SKIP_TTS_IF_EXISTS, VOICE_PREVIEW_ENABLED, TTS_PROFILES,
)
from .playback import (
    BED_ENABLED, MAIN_VOLUME_PERCENT, BED_FADE_MS, BED_DEVICE_ID,
    BED_SPOTIFY_TRACK_ID, SPOTIFY_BED_TRACK_ID, BED_FACTOR, BED_VOLUME_PERCENT,
)
from .generation import (
    BATCH_SIZE, TEMPERATURE_MAIN, TEMPERATURE_BIO,
    ENABLE_RANK_INTRO, ENABLE_TRACK_DETAIL, ENABLE_ARTIST_DETAIL,
    GENERATE_JSON_LOGGING_ENABLED, GENERATE_JSON_LOG_PATH, SPOTIFY_BLACKLIST,
)
from .logging_cfg import (
    LOG_LEVEL, LOG_SUMMARY_ENABLED, STEP_LOG_LEVELS,
    DB_QUERIES_LOG_LEVEL, LOG_LEVEL_COLLECTIONS_GENERATE,
    DEBUG_LOGGERS, LOG_LEVELS_BY_MODULE,
    LOG_FILE_ENABLED, LOG_COLOR_ENABLED, LOG_FILE_PATH,
)

# Export list: all ALLCAPS + selected helper funcs
_HELPER_EXPORTS = {
    "env_bool", "env_int", "env_list", "clamp", "extract_spotify_track_id", "spotify_creds_ok", "get_active_llm_info"
}
__all__ = [n for n in globals().keys() if n.isupper() or n in _HELPER_EXPORTS]
