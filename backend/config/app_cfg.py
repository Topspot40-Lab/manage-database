# backend/config/app_cfg.py
import os
import logging
import re

# Pull from env if present; otherwise defaults
APP_VERSION  = os.getenv("APP_VERSION", "dev")
LAST_UPDATED = os.getenv("LAST_UPDATED", "n/a")

# Call this AFTER logging is configured
def validate_app_metadata() -> None:
    log = logging.getLogger(__name__)

    if APP_VERSION == "dev":
        log.warning("APP_VERSION not set in .env; defaulting to 'dev'.")

    if LAST_UPDATED == "n/a":
        log.warning("LAST_UPDATED not set in .env; defaulting to 'n/a'.")
    else:
        # Simple YYYY-MM-DD sanity check
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", LAST_UPDATED):
            log.warning("LAST_UPDATED=%r does not match YYYY-MM-DD.", LAST_UPDATED)
