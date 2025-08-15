# backend/services/tts/generate_tts_batch.py

from pathlib import Path
import logging
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action
from backend.utils.tts_normalize import normalize_tts_text  # ⬅️ add this

logger = logging.getLogger("tts_logger")

def generate_tts_batch(
    *,
    items: list,
    text_key: str,
    voice_id: str,
    output_dir: Path,
    filename_func,
    log_prefix: str,
    overwrite: bool = False,
    play: bool = False,
    default_language: str = "en",
    normalize: bool = True,               # ⬅️ new: toggle normalization
):
    """
    Generate TTS MP3s for a batch of items.

    - Looks up the narration text from `text_key` in each item.
    - If `normalize` is True, runs the text through normalize_tts_text(...)
      using per-item `language` if present, else `default_language`.
    - Writes MP3s to `output_dir/filename_func(item)` and tags metadata.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    for item in items:
        raw_text = item.get(text_key)
        text = raw_text.strip() if isinstance(raw_text, str) else ""
        if not text:
            continue

        # Language for normalization (per-item or default)
        lang = (item.get("language") or default_language).lower()

        # Normalize just-in-time for TTS (does NOT change DB text)
        tts_text = normalize_tts_text(text, lang=lang) if normalize else text

        filename = filename_func(item)
        # be safe if filename_func forgot ".mp3"
        if not filename.lower().endswith(".mp3"):
            filename += ".mp3"
        out_path = output_dir / filename

        # Prefer track_id, fall back to artist_id, then unknown
        item_id = item.get("track_id") or item.get("spotify_artist_id") or "unknown_id"

        if out_path.exists() and not overwrite:
            log_tts_action(log_prefix, item_id, out_path, "⏭️ Skipped (exists)", play)
            continue

        logger.debug("🎧 Generating %s → %s", log_prefix, out_path)

        # Create the MP3 via ElevenLabs
        generate_tts_mp3(tts_text, out_path, voice_id, overwrite=overwrite, play=play)

        # Tag metadata (fallbacks are safe for missing fields)
        add_metadata_to_mp3(
            mp3_path=out_path,
            track_name=item.get("track_name", "Unknown"),
            artist_name=item.get("artist_name", "Unknown"),
            album_name=item.get("album_name", "TopSpot40"),
        )

        log_tts_action(log_prefix, item_id, out_path, "✅ Generated", play)
        generated.append(str(out_path))

    return {
        "message": f"✅ Generated {len(generated)} {log_prefix} files",
        "files": generated,
    }
