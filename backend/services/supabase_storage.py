# backend/services/supabase_storage.py

import logging
from backend.services.supabase_client import supabase
from backend.utils.tts_diagnostics import normalize_for_filename

logger = logging.getLogger(__name__)

async def delete_intro_mp3_files_for_combo(decade: str, genre: str):
    prefix = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_"
    logger.info(f"🧹 Deleting intro MP3s with prefix: {prefix}")

    try:
        files = supabase.storage.from_("track-intro-mp3-files").list().get("data", [])
        for file in files:
            name = file.get("name", "")
            if name.startswith(prefix):
                logger.info(f"🗑️ Deleting file: {name}")
                supabase.storage.from_("track-intro-mp3-files").remove(name)

    except Exception as e:
        logger.error(f"🔥 Error deleting intro MP3s for {decade}/{genre}: {e}")
