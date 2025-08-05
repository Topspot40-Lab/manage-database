# backend/services/supabase_playback.py

import httpx
import logging
import subprocess
import tempfile
from pathlib import Path

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

logger = logging.getLogger("supabase_playback")

async def play_mp3(bucket: str, filename: str):
    """
    Downloads an MP3 file from Supabase Storage and plays it using ffplay.
    This method:
    - Downloads the MP3 file into a temp file
    - Plays it using ffplay via subprocess
    - Deletes the temp file after playback
    """

    # Construct the Supabase file URL
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{filename}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY
    }

    try:
        logger.debug(f"📥 Downloading MP3 from Supabase: {filename}")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            logger.warning(f"⚠️ Supabase returned {response.status_code} for {url}")
            return

        # Save downloaded MP3 content to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_file.write(response.content)
            tmp_path = Path(tmp_file.name)

        logger.debug(f"🔊 Playing with ffplay: {tmp_path}")
        try:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(tmp_path)],
                check=True
            )
            logger.debug("✅ Playback completed with ffplay.")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ ffplay failed: {e}")

        # Attempt to delete the temporary file after playback
        try:
            tmp_path.unlink()
            logger.debug(f"🧹 Deleted temp file: {tmp_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not delete temp file: {e}")

    except Exception as e:
        logger.error(f"❌ Playback failed for {filename}: {type(e).__name__}: {e}")
