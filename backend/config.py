# backend/config.py

import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# === Core Paths ===
BASE_DIR = Path(__file__).resolve().parent.parent  # one level up from /backend
TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"


SCHEMA_PATH = BASE_DIR / "../schemas/track_schema.json"

# === XAI API Settings ===
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-2-latest"
TEMPERATURE_DEFAULT = 0.3

# === Prompt and Response Configuration ===
BATCH_SIZE = 10  # Tracks per prompt batch when generating intros/details
TEMPERATURE_MAIN = 0.3  # Used for track list generation (same as TEMPERATURE_DEFAULT)
TEMPERATURE_BIO = 0.5   # Used for artist bios


# === Testing Toggle ===
TEST_FILE_NUMBER = int(os.getenv("TEST_FILE_NUMBER", 0))  # 0 = live, 1+ = use test file
