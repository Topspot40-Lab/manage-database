# backend/config.py
from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# 🌱 Load .env from REAL project root (works for PyCharm, Uvicorn, scripts, tests)
# ─────────────────────────────────────────────────────────────────────────────
# config.py → backend → project root = parents[1]
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    print(f"⚠️ WARNING: .env not found at {ENV_PATH}")

log = logging.getLogger("config")

# ─────────────────────────────────────────────────────────────────────────────
# 🎵 Spotify credentials
# ─────────────────────────────────────────────────────────────────────────────
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID") or os.getenv("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET") or os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = (
    os.getenv("SPOTIFY_REDIRECT_URI")
    or os.getenv("SPOTIPY_REDIRECT_URI")
    or "http://127.0.0.1:8888/callback"
)
SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "US")

def spotify_creds_ok() -> bool:
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)

# ─────────────────────────────────────────────────────────────────────────────
# Small env helpers
# ─────────────────────────────────────────────────────────────────────────────
def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default

def _clamp(v: int, lo=0, hi=100) -> int:
    return max(lo, min(hi, v))

def _extract_spotify_track_id(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    m = re.match(r"^spotify:track:([A-Za-z0-9]{22})$", v)
    if m:
        return m.group(1)
    m = re.match(r"^https?://open\.spotify\.com/track/([A-Za-z0-9]{22})", v)
    if m:
        return m.group(1)
    v_no_q = v.split("?", 1)[0]
    if re.fullmatch(r"[A-Za-z0-9]{22}", v_no_q):
        return v_no_q
    return None

# ─────────────────────────────────────────────────────────────────────────────
# DB log level
# ─────────────────────────────────────────────────────────────────────────────
DB_QUERIES_LOG_LEVEL = os.getenv("DB_QUERIES_LOG_LEVEL", "DEBUG").upper()

# ─────────────────────────────────────────────────────────────────────────────
# App metadata
# ─────────────────────────────────────────────────────────────────────────────
APP_VERSION = "1.0.8"
LAST_UPDATED = "2025-08-10: 11:00 am"

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = ROOT_DIR
TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"
SCHEMA_PATH = BASE_DIR / "backend" / "schemas" / "track_schema.json"

# ─────────────────────────────────────────────────────────────────────────────
# 🤖 xAI LLM settings
# ─────────────────────────────────────────────────────────────────────────────
LLM_PROVIDER = "xai"
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_BASE = "https://api.x.ai/v1"
XAI_API_URL = f"{XAI_API_BASE}/chat/completions"
DEFAULT_XAI_MODEL = os.getenv("XAI_MODEL", "grok-3-latest")
XAI_MODEL = DEFAULT_XAI_MODEL

TEMPERATURE_DEFAULT = 0.3
XAI_CONNECT_TIMEOUT = env_int("XAI_CONNECT_TIMEOUT", 10)
XAI_READ_TIMEOUT    = env_int("XAI_READ_TIMEOUT", 120)
XAI_MAX_RETRIES     = env_int("XAI_MAX_RETRIES", 3)
XAI_BACKOFF_FACTOR  = float(os.getenv("XAI_BACKOFF_FACTOR", "1.5"))
XAI_TIMEOUT_SECONDS = env_int("XAI_TIMEOUT_SECONDS", XAI_READ_TIMEOUT)

FALLBACK_TO_TEST_ON_XAI_ERROR = True
FALLBACK_TEST_FILE_NUMBER = 1

# ─────────────────────────────────────────────────────────────────────────────
# 🔑 Supabase credentials
# ─────────────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# ─────────────────────────────────────────────────────────────────────────────
# Audio bucket definitions
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_BUCKETS = {
    "en": "audio-en",
    "es": "audio-es",
    "pt-BR": "audio-ptbr",
}
BUCKETS = {lang: {"intro": b, "detail": b, "artist": b} for lang, b in LANGUAGE_BUCKETS.items()}
AUDIO_PREFIXES = {"intro": "intro", "detail": "detail", "artist": "artist"}

BUCKET_TRACK_INTRO   = "track-intro-mp3-files"
BUCKET_TRACK_DETAIL  = "track-detail-mp3-files"
BUCKET_ARTIST        = "artist-mp3-files"
BUCKET_SPOTIFY_TRACK = "spotify-track-mp3-files"

SUPABASE_BUCKET_ARTIST_MP3 = BUCKETS["en"]["artist"]

# ─────────────────────────────────────────────────────────────────────────────
# JSON Generation settings
# ─────────────────────────────────────────────────────────────────────────────
BATCH_SIZE = 10
TEMPERATURE_MAIN = 0.3
TEMPERATURE_BIO  = 0.5

ENABLE_RANK_INTRO    = True
ENABLE_TRACK_DETAIL  = True
ENABLE_ARTIST_DETAIL = True

GENERATE_JSON_LOGGING_ENABLED = False
GENERATE_JSON_LOG_PATH = "backend/logs/new_json_all_decades.log"

SPOTIFY_BLACKLIST = {
    "garth brooks", "chris gaines", "bob seger",
    "king crimson", "joanna newsom"
}

# ─────────────────────────────────────────────────────────────────────────────
# 🎚 Playback “bed” mix
# ─────────────────────────────────────────────────────────────────────────────
BED_ENABLED         = env_bool("BED_ENABLED", True)
MAIN_VOLUME_PERCENT = env_int("MAIN_VOLUME_PERCENT", 60)
BED_FADE_MS         = env_int("BED_FADE_MS", 1200)
BED_DEVICE_ID       = os.getenv("BED_DEVICE_ID") or None

_bed_id_raw = (
    os.getenv("BED_SPOTIFY_TRACK_ID")
    or os.getenv("SPOTIFY_BED_TRACK_ID")
    or "2ggZjjqszgPpFUMyCwPrrj"
)
BED_SPOTIFY_TRACK_ID = _extract_spotify_track_id(_bed_id_raw)
SPOTIFY_BED_TRACK_ID = BED_SPOTIFY_TRACK_ID

_bed_factor_env = (os.getenv("BED_FACTOR") or "").strip()
BED_FACTOR: float | None = None
if _bed_factor_env:
    try:
        BED_FACTOR = float(_bed_factor_env)
    except ValueError:
        log.warning("Invalid BED_FACTOR '%s'; ignoring.", _bed_factor_env)

if BED_FACTOR is not None:
    BED_VOLUME_PERCENT = _clamp(int(round(MAIN_VOLUME_PERCENT * BED_FACTOR)))
    log.info(f"🎚 BED via factor: MAIN={MAIN_VOLUME_PERCENT}% * {BED_FACTOR} => BED={BED_VOLUME_PERCENT}%")
else:
    BED_VOLUME_PERCENT = _clamp(env_int("BED_VOLUME_PERCENT", 20))
    log.info(f"🎚 BED fixed volume: {BED_VOLUME_PERCENT}%")

# ─────────────────────────────────────────────────────────────────────────────
# 🔊 ElevenLabs TTS
# ─────────────────────────────────────────────────────────────────────────────
ELEVENLABS_ENABLE   = env_bool("ELEVENLABS_ENABLE", False)
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")

VOICE_ID_INTRO  = os.getenv("VOICE_ID_INTRO",  "EXAVITQu4vr4xnSDxMaL")
VOICE_ID_ARTIST = os.getenv("VOICE_ID_ARTIST", "Vr6EZfGAz5W6T1wn6b4p")
VOICE_ID_TRACK  = os.getenv("VOICE_ID_TRACK",  "oWAxZDx7w5VEj9dCyTzz")

VOICE_STABILITY   = float(os.getenv("VOICE_STABILITY",  "0.5"))
VOICE_SIMILARITY  = float(os.getenv("VOICE_SIMILARITY", "0.75"))

_ELEVEN_MODEL_ID_DEFAULT = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
ELEVENLABS_MODEL = _ELEVEN_MODEL_ID_DEFAULT
ELEVEN_MODEL_ID  = _ELEVEN_MODEL_ID_DEFAULT

ELEVEN_MODEL_ID_ES    = os.getenv("ELEVENLABS_MODEL_ES",    "eleven_turbo_v2_5")
ELEVEN_MODEL_ID_PT_BR = os.getenv("ELEVENLABS_MODEL_PT_BR", "eleven_turbo_v2_5")

ELEVEN_MODELS_SUPPORT_LANGUAGE = {"eleven_turbo_v2_5", "eleven_flash_v2_5"}

ELEVEN_LANGUAGE_CODE_MAP = {
    "en": "en",
    "es": "es",
    "pt-BR": "pt",
}

MODEL_BY_LANG = {
    "en":    _ELEVEN_MODEL_ID_DEFAULT,
    "es":    ELEVEN_MODEL_ID_ES,
    "pt-BR": ELEVEN_MODEL_ID_PT_BR,
}

SUPPORTED_LANGS  = ["en", "es", "pt-BR"]
DEFAULT_LANGUAGE = os.getenv("DEFAULT_TTS_LANGUAGE", "en")
DEFAULT_TTS_LANGUAGE = DEFAULT_LANGUAGE

SKIP_TTS_IF_EXISTS    = env_bool("SKIP_TTS_IF_EXISTS", True)
VOICE_PREVIEW_ENABLED = env_bool("VOICE_PREVIEW_ENABLED", False)

# ─────────────────────────────────────────────────────────────────────────────
# 🪵 Logging config
# ─────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG_LOGGERS = [s.strip() for s in (os.getenv("DEBUG_LOGGERS") or "").split(",") if s.strip()]

LOG_LEVELS_BY_MODULE = {
    "backend.services.spotify_service": "INFO",
    "backend.services.track_generator": "INFO",
    "backend.services.utils": "INFO",
    "backend.services.xai_service": "INFO",
    "backend.services.xai_api_client": "INFO",
    "backend.services.supabase_playback": "INFO",
    "backend.routers.generate_json": "INFO",
    "backend.routers.insert_json": "INFO",
    "backend.routers.load_json_track_file": "INFO",
    "backend.routers.validate_json": "INFO",
    "backend.routers.supabase_summary": "INFO",
    "backend.routers.tts_intro": "INFO",
    "backend.routers.tts_detail": "INFO",
    "backend.routers.supabase_loader": "INFO",
    "backend.routers.insert_specialty": "INFO",
    "backend.routers.generate_poprock": "INFO",
    "backend.routers.llm_client": "INFO",
    "backend.routers.collections_generate": os.getenv("LOG_LEVEL_COLLECTIONS_GENERATE", LOG_LEVEL),
    "backend.services.db_queries": DB_QUERIES_LOG_LEVEL,
    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "INFO",
    "backend.logging.track_logging": "INFO",
    "tts_logger": "INFO",
    "supabase_summary": "INFO",
    "tts_diagnostics": "INFO",
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",
}

LOG_FILE_ENABLED = env_bool("LOG_FILE_ENABLED", True)
LOG_COLOR_ENABLED = env_bool("LOG_COLOR_ENABLED", True)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "backend/logs/topspot.log")

# ─────────────────────────────────────────────────────────────────────────────
# 🔍 Diagnostics helper
# ─────────────────────────────────────────────────────────────────────────────
def get_active_llm_info() -> dict:
    return {
        "provider": LLM_PROVIDER,
        "xai_model": DEFAULT_XAI_MODEL,
        "timeouts": {
            "connect": XAI_CONNECT_TIMEOUT,
            "read": XAI_READ_TIMEOUT,
            "max_retries": XAI_MAX_RETRIES,
            "backoff_factor": XAI_BACKOFF_FACTOR,
        },
    }
