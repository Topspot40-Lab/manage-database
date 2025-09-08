# backend/services/tts/generate_tts_batch.py

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import logging

from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action
from backend.utils.tts_normalize import normalize_tts_text  # keep

logger = logging.getLogger("tts_logger")

def _safe_mp3_name(name: str) -> str:
    """
    Very small safety: trim whitespace and ensure .mp3 extension is present exactly once.
    Avoid path separators to prevent accidental nested paths.
    """
    name = (name or "").strip().replace("\\", "_").replace("/", "_")
    return name if name.lower().endswith(".mp3") else f"{name}.mp3"

def generate_tts_batch(
    *,
    items: List[Dict[str, Any]],
    text_key: str,
    voice_id: str,
    output_dir: Path,
    filename_func: Callable[[Dict[str, Any]], str],
    log_prefix: str,
    overwrite: bool = False,
    play: bool = False,
    default_language: str = "en",
    normalize: bool = True,
    # pass-through knobs to the TTS layer
    voice_settings: Optional[Dict[str, Any]] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate TTS MP3s for a batch of items.

    - Looks up narration text from `text_key` in each item.
    - If `normalize` is True, runs the text through normalize_tts_text(...)
      using per-item `language` if present, else `default_language`.
    - Writes MP3s to `output_dir/filename_func(item)` and tags metadata.
    - Passes `voice_settings`, `model_id`, and `language` to the TTS provider.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_paths: List[str] = []
    skipped_paths: List[str] = []
    error_paths: List[str] = []

    # Preview first few filenames to sanity-check SID-based naming
    try:
        preview_names = [_safe_mp3_name(filename_func(it)) for it in items[:5]]
        logger.info("📝 Preview output filenames (first %d): %s", len(preview_names), preview_names)
    except Exception as e:
        logger.warning("⚠️ Failed to preview filenames: %s", e)

    for item in items:
        raw_text = item.get(text_key)
        text = raw_text.strip() if isinstance(raw_text, str) else ""
        if not text:
            # Nothing to synthesize for this item
            logger.debug("%s: no text in '%s'; skipping item_id=%s",
                         log_prefix, text_key, item.get("track_id") or item.get("spotify_artist_id"))
            continue

        # Language for normalization (per-item or default)
        lang = (item.get("language") or default_language).lower()

        # Normalize just-in-time for TTS (does NOT change DB text)
        tts_text = normalize_tts_text(text, lang=lang) if normalize else text

        # Build filename strictly from filename_func (SID-first), never from title
        try:
            name = filename_func(item)
        except Exception as e:
            # Last-resort fallback still prioritizes SID
            sid = (item.get("spotify_track_id") or "").strip()
            name = sid or f"track_{item.get('track_id','unknown')}"
            logger.warning("⚠️ filename_func failed (%s); falling back to '%s'", e, name)

        filename = _safe_mp3_name(name)
        out_path = output_dir / filename

        # Prefer track_id, fall back to artist_id, then unknown
        item_id = item.get("track_id") or item.get("spotify_artist_id") or "unknown_id"

        if out_path.exists() and not overwrite:
            log_tts_action(log_prefix, item_id, out_path, "⏭️ Skipped (exists)", play)
            skipped_paths.append(str(out_path))
            continue

        logger.debug(
            "🎧 Generating %s → %s | voice_id=%s | model_id=%s | settings=%s | lang=%s",
            log_prefix, out_path, voice_id, model_id, voice_settings, lang
        )

        try:
            # Create/write the MP3 via your ElevenLabs wrapper (forward all knobs)
            generate_tts_mp3(
                text=tts_text,
                out_path=out_path,
                voice_id=voice_id,
                overwrite=overwrite,
                play=play,
                settings=voice_settings,   # forward profile settings
                model_id=model_id,         # forward model (e.g., eleven_turbo_v2_5)
                language=lang,             # forward language (e.g., "es")
            )

            # Tag metadata (fallbacks are safe for missing fields)
            add_metadata_to_mp3(
                mp3_path=out_path,
                track_name=item.get("track_name", "Unknown"),
                artist_name=item.get("artist_name", "Unknown"),
                album_name=item.get("album_name", "TopSpot40"),
            )

            log_tts_action(log_prefix, item_id, out_path, "✅ Generated", play)
            generated_paths.append(str(out_path))

        except Exception as e:
            logger.exception("❌ TTS generation failed for %s (%s): %s", item_id, out_path, e)
            error_paths.append(str(out_path))

    result = {
        "message": f"✅ Generated {len(generated_paths)} {log_prefix} files"
                   + (f" | ⏭️ Skipped {len(skipped_paths)}" if skipped_paths else "")
                   + (f" | ❌ Errors {len(error_paths)}" if error_paths else ""),
        "generated": len(generated_paths),
        "skipped": len(skipped_paths),
        "errors": len(error_paths),
        "files": generated_paths,
        "skipped_files": skipped_paths,
        "error_files": error_paths,
    }
    logger.info("%s summary: %s", log_prefix, result["message"])
    return result
