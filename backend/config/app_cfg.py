import os

# Pull from env if present; otherwise defaults
APP_VERSION = os.getenv("APP_VERSION", "dev")
LAST_UPDATED = os.getenv("LAST_UPDATED", "n/a")
