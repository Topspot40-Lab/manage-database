from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
import logging

logger = logging.getLogger("tts_logger")


def log_tts_action(context: str, identifier: str, path: Path, action: str, play: bool):
    """
    Logs actions related to TTS generation or playback.

    Args:
        context (str): What kind of TTS (e.g., "Artist", "Track Detail").
        identifier (str): Unique ID (e.g., artist_id or track_id).
        path (Path): File path to the MP3 file.
        action (str): What happened (e.g., "Generated", "Skipped").
        play (bool): If True, also logs that playback was triggered.
    """
    logger.info(f"[{context}] {identifier}: {action} → {path}")
    if play:
        logger.info(f"[{context}] 🔊 Playback triggered for: {path}")


def add_metadata_to_mp3(
    mp3_path: Path,
    track_name: str,
    artist_name: str,
    album_name: str,
    track_number: str = None,
    genre: str = None,
    comment: str = None
):
    """
    Adds ID3 metadata tags to an MP3 file.

    Args:
        mp3_path (Path): Path to the MP3 file.
        track_name (str): Title of the track.
        artist_name (str): Artist name.
        album_name (str): Album or collection name.
        track_number (str, optional): e.g., "5" or "5/10".
        genre (str, optional): Genre name.
        comment (str, optional): Any extra notes or descriptions.
    """
    try:
        audio = MP3(mp3_path, ID3=EasyID3)
        audio["title"] = track_name or "Unknown Title"
        audio["artist"] = artist_name or "Unknown Artist"
        audio["album"] = album_name or "TopSpot40"

        if track_number:
            audio["tracknumber"] = track_number
        if genre:
            audio["genre"] = genre
        if comment:
            audio["comment"] = comment

        audio.save()

        logger.debug(f"🔖 [TTS Metadata] Tagged '{mp3_path.name}' → "
                     f"Title: '{track_name}' | Artist: '{artist_name}' | Album: '{album_name}'"
                     f"{' | Track: ' + track_number if track_number else ''}"
                     f"{' | Genre: ' + genre if genre else ''}"
                     f"{' | Comment: ' + comment if comment else ''}")
    except Exception as e:
        logger.warning(f"❌ [TTS Metadata] Failed to tag {mp3_path.name}: {e}")