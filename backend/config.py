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

# Directory for test JSON files used in XAI-related unit tests
TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"

# Path to the JSON schema used for validating XAI track structures
SCHEMA_PATH = BASE_DIR / "../schemas/track_schema.json"

# -----------------------------------------------------------------------------
# 🔑 XAI API CONFIGURATION
# -----------------------------------------------------------------------------
XAI_API_KEY = os.getenv("XAI_API_KEY")  # Your key from x.ai
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-2-latest"  # Could be made configurable in future
TEMPERATURE_DEFAULT = 0.3  # General purpose temperature

# -----------------------------------------------------------------------------
# 🎛️ PROMPT BEHAVIOR AND GENERATION CONFIG
# -----------------------------------------------------------------------------
BATCH_SIZE = 10            # Tracks per request when generating intro/detail
TEMPERATURE_MAIN = 0.3     # Track list prompt temperature
TEMPERATURE_BIO = 0.5      # Artist biography prompt temperature

# -----------------------------------------------------------------------------
# 🧪 (REMOVED) Test File Toggle – Now controlled via CLI
# -----------------------------------------------------------------------------
# TEST_FILE_NUMBER = int(os.getenv("TEST_FILE_NUMBER", 0))  # No longer needed
