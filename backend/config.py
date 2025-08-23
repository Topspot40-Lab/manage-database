# backend/config.py

from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# 🌱 Load environment variables
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
log = logging.getLogger("config")

# ─────────────────────────────────────────────────────────────────────────────
# 📦 App metadata
# ─────────────────────────────────────────────────────────────────────────────
APP_VERSION = "1.0.8"
LAST_UPDATED = "2025-08-10: 11:00 am"

# ─────────────────────────────────────────────────────────────────────────────
# 📁 Paths
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # project root (above /backend)
TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"
SCHEMA_PATH = BASE_DIR / "backend" / "schemas" / "track_schema.json"

# ─────────────────────────────────────────────────────────────────────────────
# 🔑 Supabase
# ─────────────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# NEW: language-scoped buckets (all kinds live in the same bucket, under prefixes)
#   audio-en/intro/*.mp3,  audio-en/detail/*.mp3,  audio-en/artist/*.mp3
#   audio-es/intro/*.mp3,  audio-es/detail/*.mp3,  audio-es/artist/*.mp3
#   audio-ptbr/intro/*.mp3, audio-ptbr/detail/*.mp3, audio-ptbr/artist/*.mp3
LANGUAGE_BUCKETS = {
    "en":    "audio-en",
    "es":    "audio-es",
    "pt-BR": "audio-ptbr",
}

# Canonical map used by services: for each language, each kind resolves to the SAME bucket.
# Keys "intro/detail/artist" are kept to avoid touching call sites; code should prepend the prefix to the object key.
BUCKETS = {
    lang: {"intro": bucket, "detail": bucket, "artist": bucket}
    for lang, bucket in LANGUAGE_BUCKETS.items()
}

# (Recommended) Standard prefixes to use when building keys in code.
AUDIO_PREFIXES = {"intro": "intro", "detail": "detail", "artist": "artist"}

# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ Legacy single-purpose buckets (kept for back-compat ONLY; do not use)
#     These reflect the OLD layout (separate buckets per kind) and are retained
#     so old imports don't crash while you refactor to BUCKETS + AUDIO_PREFIXES.
# ─────────────────────────────────────────────────────────────────────────────
BUCKET_TRACK_INTRO  = "track-intro-mp3-files"
BUCKET_TRACK_DETAIL = "track-detail-mp3-files"
BUCKET_ARTIST       = "artist-mp3-files"
BUCKET_SPOTIFY_TRACK = "spotify-track-mp3-files"

# Back-compat: single bucket reference derived from BUCKETS (used by some modules)
SUPABASE_BUCKET_ARTIST_MP3 = BUCKETS["en"]["artist"]   # resolves to "audio-en"

# ─────────────────────────────────────────────────────────────────────────────
# 🤖 XAI configuration
# ─────────────────────────────────────────────────────────────────────────────
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-3-latest"
TEMPERATURE_DEFAULT = 0.3

# Timeouts / retries
XAI_CONNECT_TIMEOUT = 10
XAI_READ_TIMEOUT = 120
XAI_MAX_RETRIES = 3
XAI_BACKOFF_FACTOR = 1.5
XAI_API_BASE = "https://api.x.ai/v1"

# Back-compat: some modules import a single timeout value
XAI_TIMEOUT_SECONDS = int(os.getenv("XAI_TIMEOUT_SECONDS", str(XAI_READ_TIMEOUT)))


# Fallback behavior (dev/testing)
FALLBACK_TO_TEST_ON_XAI_ERROR = True
FALLBACK_TEST_FILE_NUMBER = 1

# ─────────────────────────────────────────────────────────────────────────────
# 🧪 Generation behavior
# ─────────────────────────────────────────────────────────────────────────────
BATCH_SIZE = 10
TEMPERATURE_MAIN = 0.3
TEMPERATURE_BIO = 0.5

ENABLE_RANK_INTRO = True
ENABLE_TRACK_DETAIL = True
ENABLE_ARTIST_DETAIL = True

GENERATE_JSON_LOGGING_ENABLED = False
GENERATE_JSON_LOG_PATH = "backend/logs/new_json_all_decades.log"

SPOTIFY_BLACKLIST = {"garth brooks", "chris gaines", "bob seger", "king crimson", "joanna newsom"}

# ─────────────────────────────────────────────────────────────────────────────
# 🎚 Optional playback / “bed” mix settings
# ─────────────────────────────────────────────────────────────────────────────
def _clamp(v: int, lo=0, hi=100) -> int:
    return max(lo, min(hi, v))

def _extract_spotify_track_id(value: str | None) -> str | None:
    """Accepts raw 22-char ID, spotify:track:ID, or https://open.spotify.com/track/ID?..."""
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

BED_ENABLED          = os.getenv("BED_ENABLED", "true").lower() == "true"
MAIN_VOLUME_PERCENT  = int(os.getenv("MAIN_VOLUME_PERCENT", "60"))
BED_FADE_MS          = int(os.getenv("BED_FADE_MS", "1200"))
BED_DEVICE_ID        = os.getenv("BED_DEVICE_ID") or None

_bed_id_raw = (
    os.getenv("BED_SPOTIFY_TRACK_ID")
    or os.getenv("SPOTIFY_BED_TRACK_ID")
    or "2ggZjjqszgPpFUMyCwPrrj"
)
BED_SPOTIFY_TRACK_ID = _extract_spotify_track_id(_bed_id_raw)
SPOTIFY_BED_TRACK_ID = BED_SPOTIFY_TRACK_ID  # back-compat alias

_bed_factor_env = os.getenv("BED_FACTOR", "").strip()
BED_FACTOR: float | None = None
if _bed_factor_env != "":
    try:
        BED_FACTOR = float(_bed_factor_env)
    except ValueError:
        log.warning("Invalid BED_FACTOR '%s'; ignoring.", _bed_factor_env)

if BED_FACTOR is not None:
    BED_VOLUME_PERCENT = _clamp(int(round(MAIN_VOLUME_PERCENT * BED_FACTOR)))
    log.info("🎚 BED via factor: MAIN=%s%% * %s => BED=%s%%",
             MAIN_VOLUME_PERCENT, BED_FACTOR, BED_VOLUME_PERCENT)
else:
    BED_VOLUME_PERCENT = _clamp(int(os.getenv("BED_VOLUME_PERCENT", "20")))
    log.info("🎚 BED fixed volume: %s%%", BED_VOLUME_PERCENT)

# ─────────────────────────────────────────────────────────────────────────────
# 🔊 ElevenLabs TTS
# ─────────────────────────────────────────────────────────────────────────────
# Global switch & API key
ELEVENLABS_ENABLE = os.getenv("ELEVENLABS_ENABLE", "false").strip().lower() in ("1", "true", "yes")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Back-compat single voice IDs (you also have per-kind profiles below)
VOICE_ID_INTRO  = os.getenv("VOICE_ID_INTRO",  "EXAVITQu4vr4xnSDxMaL")
VOICE_ID_ARTIST = os.getenv("VOICE_ID_ARTIST", "Vr6EZfGAz5W6T1wn6b4p")
VOICE_ID_TRACK  = os.getenv("VOICE_ID_TRACK",  "oWAxZDx7w5VEj9dCyTzz")

# Default tuning if a profile omits settings
VOICE_STABILITY  = float(os.getenv("VOICE_STABILITY",  "0.5"))
VOICE_SIMILARITY = float(os.getenv("VOICE_SIMILARITY", "0.75"))

# Model selection
# Global default (used for EN unless overridden)
# _ELEVEN_MODEL_ID_DEFAULT = os.getenv("ELEVENLABS_MODEL", "eleven_monolingual_v1")
_ELEVEN_MODEL_ID_DEFAULT = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
# Back-compat for older modules that import ELEVENLABS_MODEL
ELEVENLABS_MODEL = _ELEVEN_MODEL_ID_DEFAULT


# Per-language overrides via env (optional)
ELEVEN_MODEL_ID_ES    = os.getenv("ELEVENLABS_MODEL_ES",    "eleven_multilingual_v2")
ELEVEN_MODEL_ID_PT_BR = os.getenv("ELEVENLABS_MODEL_PT_BR", "eleven_multilingual_v2")

# Single-name export retained for back-compat
ELEVEN_MODEL_ID = _ELEVEN_MODEL_ID_DEFAULT

# Canonical per-language map used by services
MODEL_BY_LANG = {
    "en":    _ELEVEN_MODEL_ID_DEFAULT,
    "es":    ELEVEN_MODEL_ID_ES,
    "pt-BR": ELEVEN_MODEL_ID_PT_BR,
}

# Back-compat: single bucket references derived from BUCKETS (avoid drift)
SUPABASE_BUCKET_ARTIST_MP3 = BUCKETS["en"]["artist"]

SUPPORTED_LANGS  = ["en", "es", "pt-BR"]
DEFAULT_LANGUAGE = "en"

# Feature toggles (kept here for convenience)
SKIP_TTS_IF_EXISTS     = os.getenv("SKIP_TTS_IF_EXISTS", "true").strip().lower() == "true"
VOICE_PREVIEW_ENABLED  = os.getenv("VOICE_PREVIEW_ENABLED", "false").strip().lower() == "true"
DEFAULT_TTS_LANGUAGE   = os.getenv("DEFAULT_TTS_LANGUAGE", "en")

# Per-language, per-kind voice profiles (service uses these first)
# To override model per kind, add "model_id" to a profile entry.

# Camilo multilingual voice PGggLl3Am9ns1ICvp3DO
TTS_PROFILES = {
    "en": {
        "intro":  {"voice_id": "BYzs2jBcHhCzX4QmS6fd",  "settings": {"stability": 0.5,  "similarity_boost": 0.8, "style": 0.4,  "use_speaker_boost": True}},
        "detail": {"voice_id": "4XUsiqPDK4UACIM2BILe", "settings": {"stability": 0.6,  "similarity_boost": 0.6, "style": 0.2,  "use_speaker_boost": False}},
        "artist": {"voice_id": "oWAxZDx7w5VEj9dCyTzz", "settings": {"stability": 0.55, "similarity_boost": 0.7, "style": 0.35, "use_speaker_boost": True}},
    },
    "es": {
        "intro":  {"voice_id": "pNInz6obpgDQGcFmaJgB",  "settings": {"stability": 0.5,  "similarity_boost": 0.85, "style": 0.5,  "use_speaker_boost": True}},
        "detail": {"voice_id": "7EjKsW93fhgPskc2LsT1", "settings": {"stability": 0.65, "similarity_boost": 0.7,  "style": 0.25, "use_speaker_boost": False}},
        "artist": {"voice_id": "w7IU2bIH6xHcyfkUUWi3", "settings": {"stability": 0.6,  "similarity_boost": 0.8,  "style": 0.4,  "use_speaker_boost": True}},
    },
    "pt-BR": {
        "intro":  {"voice_id": "5dF3gH7abcXYZ1234567",  "settings": {"stability": 0.5,  "similarity_boost": 0.85, "style": 0.5,  "use_speaker_boost": True}},
        "detail": {"voice_id": "cyD08lEy76q03ER1jZ7y", "settings": {"stability": 0.65, "similarity_boost": 0.7,  "style": 0.25, "use_speaker_boost": False}},
        "artist": {"voice_id": "CstacWqMhJQlnfLPxRG4", "settings": {"stability": 0.6,  "similarity_boost": 0.8,  "style": 0.4,  "use_speaker_boost": True}},
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 🪵 Logging configuration
# ─────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_SUMMARY_ENABLED = os.getenv("LOG_SUMMARY_ENABLED", "false").lower() == "true"

LOG_LEVEL_OVERRIDES = {
    # ────────────────────────────── STEP 1 ──────────────────────────────
    "STEP_1": "INFO",
    "STEP_1.A": "INFO",
    "STEP_1.B": "INFO",
    "STEP_1.C": "INFO",

    # ────────────────────────────── STEP 3 ──────────────────────────────
    "STEP_3": "INFO",
    "STEP_3.A": "INFO",
    "STEP_3.B": "INFO",

    # ────────────────────────────── STEP 4 ──────────────────────────────
    "STEP_4": "INFO",
    "STEP_4.A": "INFO",
    "STEP_4.B": "INFO",
    "STEP_4.C": "INFO",
    "STEP_4.D": "INFO",
    "STEP_4.E": "INFO",

    "STEP_5": "INFO",
    "STEP_6": "INFO",
    "STEP_7": "INFO",
    "STEP_8": "INFO",

    # ────────────────────────────── STEP 9 ──────────────────────────────
    "STEP_9": "INFO",
    "STEP_9.A": "INFO",
    "STEP_9.B": "INFO",
    "STEP_9.C": "INFO",

    "STEP_10": "INFO",
    "STEP_11": "INFO",
}
STEP_LOG_LEVELS = LOG_LEVEL_OVERRIDES

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
    "backend.routers.supabase_summary": "DEBUG",
    "backend.routers.tts_intro": "INFO",
    "backend.routers.tts_detail": "DEBUG",
    "backend.routers.supabase_loader": "DEBUG",
    "backend.routers.insert_specialty": "DEBUG",
    "backend.routers.generate_poprock": "DEBUG",
    "backend.routers.llm_client": "DEBUG",

    # Utilities
    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "DEBUG",

    # Custom
    "backend.logging.track_logging": "INFO",
    "tts_logger": "DEBUG",
    "supabase_summary": "INFO",
    "tts_diagnostics": "DEBUG",

    # Third-party
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",
}

LOG_FILE_ENABLED = os.getenv("LOG_FILE_ENABLED", "true").strip().lower() == "true"
LOG_COLOR_ENABLED = os.getenv("LOG_COLOR_ENABLED", "true").strip().lower() == "true"
LOG_FILE_PATH = "backend/logs/topspot.log"
