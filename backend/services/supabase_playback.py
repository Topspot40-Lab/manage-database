# backend/services/supabase_playback.py

import asyncio
import logging

logger = logging.getLogger("supabase_playback")

async def play_mp3(bucket: str, filename: str):
    logger.info(f"🎧 [MOCK] Would play {filename} from bucket {bucket}")
    await asyncio.sleep(1.0)  # simulate playback delay
