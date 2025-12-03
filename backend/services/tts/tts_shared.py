# backend/services/tts/tts_shared.py

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

logger = logging.getLogger("tts_logger")


# ─────────────────────────────────────────────
# Write MP3 metadata (track/artist/album)
# ─────────────────────────────────────────────
def add_metadata_to_mp3(
    file_path: Path,
    title: str,
    artist: str,
    album: str
) -> None:
    """
    Add metadata tags to the generated MP3 file.
    Uses mutagen to write ID3 tags.
    """
    try:
        if not file_path.exists():
            logger.warning(f"⚠️ Cannot write metadata — MP3 does not exist: {file_path}")
            return

        audio = MP3(file_path, ID3=EasyID3)

        audio["title"] = title
        audio["artist"] = artist
        audio["album"] = album

        audio.save()
        logger.debug(f"💾 Added metadata | {file_path.name} | {title} — {artist}")

    except Exception as e:
        logger.error(f"❌ Failed to add metadata to {file_path}: {e}")


# ─────────────────────────────────────────────
# Unified logging helper for TTS actions
# ─────────────────────────────────────────────
def log_tts_action(
    action_type: str,
    track_id: str,
    out_path: Path,
    status: str,
    play_requested: bool
) -> None:
    """
    Log a standardized TTS action line.
    Example:
    🎙️ Track Intro | 3n3Ppam7vgaVa1iaRUc9Lp → output.mp3 | ✅ Generated | play=False
    """
    logger.info(
        f"🎙️ {action_type} | {track_id} → {out_path.name} | {status} | play={play_requested}"
    )
