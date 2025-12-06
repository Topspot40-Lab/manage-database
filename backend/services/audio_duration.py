# backend/services/audio_duration.py
from __future__ import annotations

import httpx
import logging
from io import BytesIO
from typing import Optional

from mutagen.mp3 import MP3

# Public bucket base — same for all projects
from backend.config import SUPABASE_URL

logger = logging.getLogger(__name__)


async def get_mp3_duration_ms(bucket: str, key: str) -> Optional[int]:
    """
    Downloads the MP3 file using GET (not HEAD) and extracts the true duration
    using Mutagen. Works with ElevenLabs MP3s and Supabase public buckets.
    """
    if not bucket or not key:
        return None

    # Public-access URL (no headers required)
    url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{key}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(url)

        if res.status_code != 200:
            logger.warning("⚠️ GET request failed for %s/%s (%s)",
                           bucket, key, res.status_code)
            return None

        data = BytesIO(res.content)

        # Let Mutagen read actual MP3 header info
        audio = MP3(data)
        duration_ms = int(audio.info.length * 1000)

        return duration_ms

    except Exception as e:
        logger.error("❌ Error computing MP3 duration for %s/%s: %s",
                     bucket, key, e)
        return None
