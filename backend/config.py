# backend/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file

load_dotenv()

# config.py

APP_VERSION = "1.0.4"
LAST_UPDATED = "2025-06-28: 11:00 am"

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
ENABLE_ARTIST_DESCRIPTION = False
ENABLE_TRACK_DESCRIPTION = False
ENABLE_RANK_INTRO = False

# config.py
GENERATE_JSON_LOGGING_ENABLED = True  # ✅ Toggle logging of generate-json summary
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
STEP_LOG_LEVELS = {
    "STEP_1": "INFO",         # Overall Step 1 logging
    "STEP_1.A": "INFO",      # Prompt building
    "STEP_1.B": "INFO",      # Markdown cleanup
    "STEP_1.B.1": "INFO",    # JSON parsing
    "STEP_1.C": "INFO",       # Validation + de-duping
    # Add more steps/substeps here...
}

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
LOG_FILE_PATH = "topspot.log"
