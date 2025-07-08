# backend/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file

load_dotenv()

# config.py

APP_VERSION = "1.0.6"
LAST_UPDATED = "2025-07-06: 11:00 am"

# -----------------------------------------------------------------------------
# 📁 PATH SETTINGS
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # Root directory (above /backend)

TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"
SCHEMA_PATH = BASE_DIR / "backend" / "schemas" / "track_schema.json"


# -----------------------------------------------------------------------------
# 🔑 XAI API CONFIGURATION
# -----------------------------------------------------------------------------
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-2-latest"
TEMPERATURE_DEFAULT = 0.3

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
# 📋 FEATURE FLAGS (Text Generation)
# -----------------------------------------------------------------------------
ENABLE_ARTIST_DESCRIPTION = True
ENABLE_TRACK_DESCRIPTION = True
ENABLE_RANK_INTRO = True

# config.py
GENERATE_JSON_LOGGING_ENABLED = False  # ✅ Toggle logging of generate-json summary
GENERATE_JSON_LOG_PATH = "backend/logs/new_json_all_decades.log"


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

    # ────────────────────────────── STEP 2 ──────────────────────────────
    # ✍️ Description Generation — generates intros and details for each track

    "STEP_2":    "INFO",  # 🔁 Overall STEP 2 orchestration (XAI + bio)

    "STEP_2.A":  "INFO",  # 🅰️ Rank intro generation
    # Function: get_track_descriptions_from_xai(...)
    # Handles: `intro` field (1-liner with rank, artist, genre, etc.)

    "STEP_2.B":  "INFO",  # 🅱️ Track detail generation
    # Handles: `detail` field (Casey Kasem-style narrative)

    "STEP_2.C":  "INFO",  # 🎙️ Artist bio generation
    # Handles: `artist_description` field (stored per artist)

    # ────────────────────────────── STEP 3 ──────────────────────────────
    # 🎧 Spotify Enrichment Pipeline — enhances basic track data with Spotify metadata

    "STEP_3": "INFO",       # Top-level orchestration (called from generate_track_json)

    "STEP_3.A": "INFO",     # 🔍 STEP 3.A — Spotify Track Matching
                            # Function: get_spotify_data(base)
                            # - Calls Spotipy to search for matching track and artist
                            # - Applies fallback logic and filtering

    "STEP_3.B": "DEBUG",     # 🧱 STEP 3.B — Build Enriched Track Entry
                            # Function: enrich_track(base, spotify_match)
                            # - Merges XAI data with Spotify metadata into unified structure


    # ────────────────────────────── STEP 4 ──────────────────────────────
    # 📦 Final JSON Builder — assembles full TopSpot data structure (track, artist, ranking)

    "STEP_4": "DEBUG",      # Orchestrator: build_final_json(enriched_tracks, request, now)

    "STEP_4.A": "DEBUG",    # 🧹 STEP 4.A — Normalize & Verify Fields
                            # Function: normalize_keys(base)
                            # - Ensures consistent field names (snake_case)
                            # - Validates presence of spotify_data and logs enrichment status

    "STEP_4.B": "DEBUG",    # 🧪 STEP 4.B — Build Track Table Entries
                            # Function: build_track_entry(base, request, spotify_data, now)
                            # - Converts one enriched track into a row for the track table
                            # - Logs duration, artwork, and ID fields

    "STEP_4.C": "DEBUG",    # 🎙️ STEP 4.C — Build Artist Table Entries
                            # Function: build_artist_entry(...) — likely inside build_final_json
                            # - Deduplicates artists and creates a record for each
                            # - Optionally includes Spotify ID, description, and artwork

    "STEP_4.D": "DEBUG",    # 🏆 STEP 4.D — Build Ranking Table Entries
                            # Function: build_ranking_entry(base, track_entry, request, now)
                            # - Builds rank entry including track_id, genre, decade, and intro/detail

    "STEP_4.E": "DEBUG",    # 📦 STEP 4.E — Final JSON Assembly
                            # Function: build_final_json(...) — final return step
                            # - Combines all tables: core_tables, track_tables, ranking_tables
                            # - Outputs full JSON object and summary log


    "STEP_5": "INFO",      # Replace missing Spotify tracks
    "STEP_6": "INFO",      # Remove tracks still missing Spotify data
    "STEP_7": "INFO",      # Add spare tracks
    "STEP_8": "INFO",      # Reassign ranks
    "STEP_9": "INFO",      # Rebuild artist table
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
    "backend.services.xai_service": "INFO",
    "backend.services.spotify_service": "INFO",
    "backend.services.track_generator": "INFO",
    "backend.services.utils": "INFO",
    "backend.logging.track_logging": "INFO",
    "backend.routers.validate_json": "INFO",
    "backend.utils.track_builder": "INFO",
    "backend.utils.normalize": "INFO",
    "spotipy": "WARNING",
    "urllib3": "WARNING",
    "requests": "WARNING",
    "httpx": "WARNING",
}

# ---------------------------------------------------------------------------
# 🎨 TERMINAL AND FILE LOGGING OPTIONS (controlled by .env)
# ---------------------------------------------------------------------------
LOG_FILE_ENABLED = os.getenv("LOG_FILE_ENABLED", "true").strip().lower() == "true"
LOG_COLOR_ENABLED = os.getenv("LOG_COLOR_ENABLED", "true").strip().lower() == "true"
LOG_FILE_PATH = "backend/logs/topspot.log"

