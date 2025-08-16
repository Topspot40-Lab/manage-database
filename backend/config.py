# backend/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file

load_dotenv()

# config.py

APP_VERSION = "1.0.8"
LAST_UPDATED = "2025-08-10: 11:00 am"

# ---------------------------------------------------------------------
# 🎧 TRACK LIMIT CONFIG
# ---------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# -----------------------------------------------------------------------------
# 📁 PATH SETTINGS
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # Root directory (above /backend)

TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"
SCHEMA_PATH = BASE_DIR / "backend" / "schemas" / "track_schema.json"

import os

# BED_ENABLED          = os.getenv("BED_ENABLED", "true").lower() == "true"
# SPOTIFY_BED_TRACK_ID = os.getenv("SPOTIFY_BED_TRACK_ID", "2ggZjjqszgPpFUMyCwPrrj")  # your bed track
# BED_VOLUME_PERCENT   = int(os.getenv("BED_VOLUME_PERCENT", "20"))   # 0–100
# MAIN_VOLUME_PERCENT  = int(os.getenv("MAIN_VOLUME_PERCENT", "60"))  # after VO
# BED_FADE_MS          = int(os.getenv("BED_FADE_MS", "1200"))        # fade-out time
# BED_DEVICE_ID        = os.getenv("BED_DEVICE_ID", "")               # optional pin to device
# BED_FACTOR           = os.getenv("BED_FACTOR", "")               # optional pin to device


# -----------------------------------------------------------------------------
# 🔑 XAI API CONFIGURATION
# -----------------------------------------------------------------------------
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-3-latest"
TEMPERATURE_DEFAULT = 0.3

# === Supabase Storage Buckets ===
BUCKET_TRACK_INTRO = "track-intro-mp3-files"
BUCKET_TRACK_DETAIL = "track-detail-mp3-files"
BUCKET_ARTIST = "artist-mp3-files"
BUCKET_SPOTIFY_TRACK = "spotify-track-mp3-files"


# -----------------------------------------------------------------------------
# 🎛️ PROMPT BEHAVIOR AND GENERATION CONFIG
# -----------------------------------------------------------------------------
BATCH_SIZE = 10
TEMPERATURE_MAIN = 0.3
TEMPERATURE_BIO = 0.5

# -----------------------------------------------------------------------------
# 🧪 (REMOVED) Test File Toggle – Now controlled via CLI
# -----------------------------------------------------------------------------
TEST_FILE_NUMBER = 1

# -----------------------------------------------------------------------------
# 📋 FEATURE FLAGS (Text Generation) for generate-json endpoint
# -----------------------------------------------------------------------------
ENABLE_RANK_INTRO = True
ENABLE_TRACK_DETAIL = True
ENABLE_ARTIST_DETAIL = True


# config.py
GENERATE_JSON_LOGGING_ENABLED = False  # ✅ Toggle logging of generate-json summary
GENERATE_JSON_LOG_PATH = "backend/logs/new_json_all_decades.log"

# ---------------------------------------------------------------------------
# 🔊 ELEVENLABS TEXT-TO-SPEECH CONFIGURATION
# ---------------------------------------------------------------------------

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Voice IDs for different types of narration
VOICE_ID_INTRO = os.getenv("VOICE_ID_INTRO", "EXAVITQu4vr4xnSDxMaL")
VOICE_ID_ARTIST = os.getenv("VOICE_ID_ARTIST", "Vr6EZfGAz5W6T1wn6b4p")
VOICE_ID_TRACK = os.getenv("VOICE_ID_TRACK", "oWAxZDx7w5VEj9dCyTzz")

# Brian nPczCjzI2devNBz1zQrb
# George JBFqnCBsd6RMkjVDRZzb
# Daniel onwK4e9ZLuTAKqWW03F9
# Bill pqHfZKP75CvOlQylNhV4

# Audio tuning parameters
VOICE_STABILITY = float(os.getenv("VOICE_STABILITY", 0.5))
VOICE_SIMILARITY = float(os.getenv("VOICE_SIMILARITY", 0.75))

# Model used for generation
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_monolingual_v1")

# Optional behavior toggles
SKIP_TTS_IF_EXISTS = os.getenv("SKIP_TTS_IF_EXISTS", "true").strip().lower() == "true"
VOICE_PREVIEW_ENABLED = os.getenv("VOICE_PREVIEW_ENABLED", "false").strip().lower() == "true"
DEFAULT_TTS_LANGUAGE = os.getenv("DEFAULT_TTS_LANGUAGE", "en")

SPOTIFY_BLACKLIST = {"garth brooks", "chris gaines", "bob seger", "king crimson", "joanna newsom"}



# ---------------------------------------------------------------------------
# 📡 LOGGING CONFIGURATION
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # Global fallback log level
LOG_SUMMARY_ENABLED = os.getenv("LOG_SUMMARY_ENABLED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# 🔍 STEP-WISE LOGGING CONFIGURATION
# These loggers should be used like:
#   logger = logging.getLogger("STEP_1.B.1")
#
# You can turn on just one sub-step to DEBUG and leave others at INFO
# Inheritance applies (e.g., STEP_1 sets default for STEP_1.*, etc.)
# ---------------------------------------------------------------------------

LOG_LEVEL_OVERRIDES = {

    # ────────────────────────────── STEP 1 ──────────────────────────────
    # 🧠 Track Generation via XAI — fetch initial track list from AI or test file

    "STEP_1": "INFO",  # Top-level orchestration for AI track generation

    "STEP_1.A": "INFO",  # 🧠 STEP 1.A — Request Track List from XAI
    # Function: get_top_tracks_from_xai(prompt, ...)
    # - Sends structured prompt to XAI
    # - Receives raw list of track/artist results

    "STEP_1.B": "INFO",  # 🧹 STEP 1.B — Parse + Filter AI Response
    # Function: parse_and_filter_tracks(json_input, num_tracks, is_test_mode)
    # - Parses JSON from XAI
    # - Filters out invalid or duplicate entries
    # - Trims down to `num_tracks` unless in test mode

    "STEP_1.C": "INFO",  # 🧹 STEP 1.C
        # ────────────────────────────── STEP 3 ──────────────────────────────
    # 🎧 Spotify Enrichment Pipeline — enhances basic track data with Spotify metadata

    "STEP_3": "INFO",       # Top-level orchestration (called from generate_track_json)

    "STEP_3.A": "INFO",     # 🔍 STEP 3.A — Spotify Track Matching
                            # Function: get_spotify_data(base)
                            # - Calls Spotipy to search for matching track and artist
                            # - Applies fallback logic and filtering

    "STEP_3.B": "INFO",     # 🧱 STEP 3.B — Build Enriched Track Entry
                            # Function: enrich_track(base, spotify_match)
                            # - Merges XAI data with Spotify metadata into unified structure


    # ────────────────────────────── STEP 4 ──────────────────────────────
    # 📦 Final JSON Builder — assembles full TopSpot data structure (track, artist, ranking)

    "STEP_4": "INFO",      # Orchestrator: build_final_json(enriched_tracks, request, now)

    "STEP_4.A": "INFO",    # 🧹 STEP 4.A — Normalize & Verify Fields
                            # Function: normalize_keys(base)
                            # - Ensures consistent field names (snake_case)
                            # - Validates presence of spotify_data and logs enrichment status

    "STEP_4.B": "INFO",    # 🧪 STEP 4.B — Build Track Table Entries
                            # Function: build_track_entry(base, request, spotify_data, now)
                            # - Converts one enriched track into a row for the track table
                            # - Logs duration, artwork, and ID fields

    "STEP_4.C": "INFO",    # 🎙️ STEP 4.C — Build Artist Table Entries
                            # Function: build_artist_entry(...) — likely inside build_final_json
                            # - Deduplicates artists and creates a record for each
                            # - Optionally includes Spotify ID, description, and artwork

    "STEP_4.D": "INFO",    # 🏆 STEP 4.D — Build Ranking Table Entries
                            # Function: build_ranking_entry(base, track_entry, request, now)
                            # - Builds rank entry including track_id, genre, decade, and intro/detail

    "STEP_4.E": "INFO",    # 📦 STEP 4.E — Final JSON Assembly
                            # Function: build_final_json(...) — final return step
                            # - Combines all tables:
                            # - Outputs full JSON object and summary log


    "STEP_5": "INFO",      # Replace missing Spotify tracks
    "STEP_6": "INFO",      # Remove tracks still missing Spotify data
    "STEP_7": "INFO",      # Add spare tracks
    "STEP_8": "INFO",      # Reassign ranks

    # ────────────────────────────── STEP 9 ──────────────────────────────
    # ✍️ Description Generation — generates intros and details for each track

    "STEP_9": "INFO",  # 🔁 Overall STEP 2 orchestration (XAI + bio)

    "STEP_9.A": "INFO",  # 🅰️ Rank intro generation
    # Function: get_track_descriptions_from_xai(...)
    # Handles: `intro` field (1-liner with rank, artist, genre, etc.)

    "STEP_9.B": "INFO",  # 🅱️ Track detail generation
    # Handles: `detail` field (Casey Kasem-style narrative)

    "STEP_9.C": "INFO",  # 🎙️ Artist bio generation
    # Handles: `artist_description` field (stored per artist)

    # "STEP_9": "INFO",      # Rebuild artist table
    "STEP_10": "INFO",     # Save final JSON to disk
    "STEP_11": "INFO"      # Print summary to terminal

    # Add more steps/sub-steps here...
}
STEP_LOG_LEVELS = LOG_LEVEL_OVERRIDES

# ---------------------------------------------------------------------------
# 🧩 MODULE-SPECIFIC LOG LEVEL OVERRIDES
# You can still override individual modules by name.
# These work independently of STEP loggers.
# ---------------------------------------------------------------------------
LOG_LEVELS_BY_MODULE = {
    # ─────────────────────────────
    # 🧩 Core Backend Services
    # ─────────────────────────────
    "backend.services.spotify_service": "INFO",
    "backend.services.track_generator": "INFO",
    "backend.services.utils": "INFO",
    "backend.services.xai_service": "INFO",
    "backend.services.xai_api_client": "INFO",
    "backend.services.supabase_playback": "INFO",       # ✅ Added

    # ─────────────────────────────
    # 🧱 Routers
    # ─────────────────────────────
    "backend.routers.generate_json": "INFO",
    "backend.routers.insert_json": "INFO",
    "backend.routers.load_json_track_file": "INFO",
    "backend.routers.validate_json": "INFO",
    "backend.routers.supabase_summary": "INFO",
    "backend.routers.tts_intro": "INFO",
    "backend.routers.tts_detail": "DEBUG",
    "backend.routers.supabase_loader": "DEBUG",          # ✅ Added
    "backend.routers.insert_specialty": "DEBUG",  # ✅ Added for specialty JSON insert

    # ─────────────────────────────
    # 🧰 Utility Modules
    # ─────────────────────────────
    "backend.utils.normalize": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.tts_diagnostics": "DEBUG",

    # ─────────────────────────────
    # 🪵 Custom Loggers
    # ─────────────────────────────
    "backend.logging.track_logging": "INFO",
    "tts_logger": "DEBUG",
    "supabase_summary": "INFO",
    "tts_diagnostics": "DEBUG",

    # ─────────────────────────────
    # 🌐 Third-party Libraries
    # ─────────────────────────────
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING"
}

# ---------------------------------------------------------------------------
# 🎨 TERMINAL AND FILE LOGGING OPTIONS (controlled by .env)
# ---------------------------------------------------------------------------
LOG_FILE_ENABLED = os.getenv("LOG_FILE_ENABLED", "true").strip().lower() == "true"
LOG_COLOR_ENABLED = os.getenv("LOG_COLOR_ENABLED", "true").strip().lower() == "true"
LOG_FILE_PATH = "backend/logs/topspot.log"

# 🔊 Supabase Bucket for Artist MP3s
SUPABASE_BUCKET_ARTIST_MP3 = BUCKET_ARTIST

# ---------------------------------------------------------------------------
# 🛟 XAI Fallback & Timeout Configuration
# ---------------------------------------------------------------------------

# If True, when XAI fails (quota/rate limit or network), the system will load a local test JSON instead.
FALLBACK_TO_TEST_ON_XAI_ERROR = True   # default: True for dev/testing

# Which test file number to use when falling back (must exist in TEST_JSON_DIR)
FALLBACK_TEST_FILE_NUMBER = 1          # e.g., json_test_file_1.json

# Timeout (in seconds) for XAI API requests
XAI_TIMEOUT_SECONDS = 180


import os
import re
import logging

log = logging.getLogger("config")

def _clamp(v: int, lo=0, hi=100) -> int:
    return max(lo, min(hi, v))

def _extract_spotify_track_id(value: str | None) -> str | None:
    """Accepts raw 22-char ID, spotify:track:ID, or https://open.spotify.com/track/ID?...."""
    if not value:
        return None
    v = value.strip()
    # spotify:track:ID
    m = re.match(r"^spotify:track:([A-Za-z0-9]{22})$", v)
    if m:
        return m.group(1)
    # full URL
    m = re.match(r"^https?://open\.spotify\.com/track/([A-Za-z0-9]{22})", v)
    if m:
        return m.group(1)
    # raw ID (maybe with ?si=..)
    v_no_q = v.split("?", 1)[0]
    if re.fullmatch(r"[A-Za-z0-9]{22}", v_no_q):
        return v_no_q
    return None

# ----------------- env -----------------
BED_ENABLED          = os.getenv("BED_ENABLED", "true").lower() == "true"
MAIN_VOLUME_PERCENT  = int(os.getenv("MAIN_VOLUME_PERCENT", "60"))
BED_FADE_MS          = int(os.getenv("BED_FADE_MS", "1200"))
BED_DEVICE_ID        = os.getenv("BED_DEVICE_ID") or None

# Track ID: accept either key; normalize to a clean raw ID
_bed_id_raw = (
    os.getenv("BED_SPOTIFY_TRACK_ID") or
    os.getenv("SPOTIFY_BED_TRACK_ID") or
    "2ggZjjqszgPpFUMyCwPrrj"  # default you showed
)
BED_SPOTIFY_TRACK_ID = _extract_spotify_track_id(_bed_id_raw)

if BED_ENABLED and not BED_SPOTIFY_TRACK_ID:
    log.warning("BED_ENABLED=true but no valid BED_SPOTIFY_TRACK_ID parsed from env.")

# (optional back-compat for any older imports)
SPOTIFY_BED_TRACK_ID = BED_SPOTIFY_TRACK_ID

# Volume: BED_FACTOR (float) takes precedence; else BED_VOLUME_PERCENT
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

# --- XAI timeouts & retries ---
XAI_CONNECT_TIMEOUT = 10     # seconds
XAI_READ_TIMEOUT = 120       # bump from 30 -> 120 (or 180)
XAI_MAX_RETRIES = 3
XAI_BACKOFF_FACTOR = 1.5
# Optional: force regional endpoint (see note below)
# XAI_API_BASE = "https://us-east-1.api.x.ai/v1"
XAI_API_BASE = "https://api.x.ai/v1"

# backend/config.py
BUCKETS = {
    "en": {"intro": "track-intro-mp3-files",    "detail": "track-detail-mp3-files",    "artist": "artist-mp3-files"},
    "es": {"intro": "track-intro-mp3-files-es", "detail": "track-detail-mp3-files-es", "artist": "artist-mp3-files-es"},
    "pt": {"intro": "track-intro-mp3-files-pt", "detail": "track-detail-mp3-files-pt", "artist": "artist-mp3-files-pt"},
}
SUPPORTED_LANGS = ["en", "es", "pt-BR"]
DEFAULT_LANGUAGE = "en"

ELEVEN_MODEL_ID = "eleven_multilingual_v2"  # good for EN/ES/PT-BR

# One voice per language × kind (fill in your real voice_ids)
TTS_PROFILES = {
    "en": {
        "intro":  {"voice_id": "<EN_INTRO_ID>",  "settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.4, "use_speaker_boost": True}},
        "detail": {"voice_id": "<EN_DETAIL_ID>", "settings": {"stability": 0.6, "similarity_boost": 0.6, "style": 0.2, "use_speaker_boost": False}},
        "artist": {"voice_id": "<EN_ARTIST_ID>", "settings": {"stability": 0.55,"similarity_boost": 0.7, "style": 0.35,"use_speaker_boost": True}},
    },
    "es": {
        "intro":  {"voice_id": "<ES_INTRO_ID>",  "settings": {"stability": 0.5, "similarity_boost": 0.85,"style": 0.5, "use_speaker_boost": True}},
        "detail": {"voice_id": "<ES_DETAIL_ID>", "settings": {"stability": 0.65,"similarity_boost": 0.7, "style": 0.25,"use_speaker_boost": False}},
        "artist": {"voice_id": "<ES_ARTIST_ID>", "settings": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.4, "use_speaker_boost": True}},
    },
    "pt-BR": {
        "intro":  {"voice_id": "<PT_INTRO_ID>",  "settings": {"stability": 0.5, "similarity_boost": 0.85,"style": 0.5, "use_speaker_boost": True}},
        "detail": {"voice_id": "<PT_DETAIL_ID>", "settings": {"stability": 0.65,"similarity_boost": 0.7, "style": 0.25,"use_speaker_boost": False}},
        "artist": {"voice_id": "<PT_ARTIST_ID>", "settings": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.4, "use_speaker_boost": True}},
    },
}
