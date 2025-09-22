from __future__ import annotations

import logging
from backend.services.supabase_storage import delete_intro_mp3_files_for_combo

logger = logging.getLogger(__name__)

def maybe_reset_intro_mp3s(*, reset: bool, decade_name: str, genre_name: str, languages=("en",), dry_run=False):
    if not reset:
        return
    try:
        report = delete_intro_mp3_files_for_combo(
            decade_name, genre_name,
            languages=languages,
            dry_run=dry_run
        )
        logger.info("Intro MP3 cleanup report: %s", report)
    except Exception as e:
        logger.error("Storage cleanup failed: %s", e)
