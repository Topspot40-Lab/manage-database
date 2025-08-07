from pathlib import Path
import logging
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action

logger = logging.getLogger("tts_logger")

def generate_tts_batch(
    items: list,
    text_key: str,
    voice_id: str,
    output_dir: Path,
    filename_func,
    log_prefix: str,
    overwrite=False,
    play=False
):
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for item in items:
        raw_text = item.get(text_key)
        text = raw_text.strip() if isinstance(raw_text, str) else ""
        if not text:
            continue

        filename = filename_func(item)
        out_path = output_dir / filename

        item_id = item.get("track_id") or item.get("spotify_artist_id") or "unknown_id"

        if out_path.exists() and not overwrite:
            log_tts_action(log_prefix, item_id, out_path, "⏭️ Skipped (exists)", play)
            continue

        logger.debug(f"🎧 Generating {log_prefix} → {out_path}")
        generate_tts_mp3(text, out_path, voice_id, overwrite=overwrite, play=play)

        # ✅ Updated: Use keyword args with fallbacks
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
        "files": generated
    }
