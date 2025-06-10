# backend/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------------------------------------------
# 📁 PATH SETTINGS
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # Root directory (above /backend)

TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"
SCHEMA_PATH = BASE_DIR / "../schemas/track_schema.json"

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

# -----------------------------------------------------------------------------
# 📡 LOGGING CONFIGURATION
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # Global default (can override via .env)

LOG_LEVELS_BY_MODULE = {
    "backend.services.xai_service": "DEBUG",
    "backend.services.spotify_service": "WARNING",
    "backend.services.utils": "INFO",
    # Add more modules as needed
}

# -----------------------------------------------------------------------------
# 🎨 LOGGING OPTIONS (via .env)
# -----------------------------------------------------------------------------
LOG_FILE_ENABLED = os.getenv("LOG_FILE_ENABLED", "True") == "True"
LOG_COLOR_ENABLED = os.getenv("LOG_COLOR_ENABLED", "True") == "True"
LOG_FILE_PATH = "topspot.log"
