from fastapi import APIRouter, Query
from pathlib import Path
import logging

from backend.services.track_cache import get_all_rank_entries
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_INTRO
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action

logger = logging.getLogger("tts_logger")

# === Intro TTS ===
intro_router = APIRouter(
    prefix="/tts/intro",
    tags=["TTS - Intro"]
)

@intro_router.post("/by-rank")
def generate_intro_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    """
    Generate TTS for the 'intro' field of ranked tracks in the specified range.
    """
    logger.debug(f"🎙️ Mr Ed ... [Intro TTS] Requested ranks {start_rank} to {end_rank} | overwrite={overwrite} | play={play}")

    rankings = get_all_rank_entries()
    output_dir = Path("data/mp3_files/track_intro_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for track in rankings:
        rank = track.get("rank")
        intro = track.get("intro", "").strip()
        track_id = track.get("track_id")

        logger.debug(f"🔍 Rank {rank}: intro={bool(intro)} | track_id={track_id} | overwrite={overwrite}")

        if not rank or not (start_rank <= rank <= end_rank):
            logger.debug(f"⏭️ Skipping rank {rank}: outside requested range")
            continue

        if not intro:
            logger.warning(f"⚠️ No intro for rank {rank} — skipping TTS")
            continue

        if not track_id:
            logger.warning(f"⚠️ No track_id for rank {rank} — skipping TTS")
            continue

        out_path = output_dir / f"{track_id}.mp3"

        if out_path.exists() and not overwrite:
            logger.debug(f"⏭️ MP3 exists and overwrite=False for {track_id}")
            log_tts_action("Track Intro", track_id, out_path, "⏭️ Skipped (exists)", play)
            continue

        logger.debug(f"🎧 Generating TTS for rank {rank}: {intro[:60]}...")
        generate_tts_mp3(intro, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)

        track_name = track.get("track_name", "Unknown Track")
        artist_name = track.get("artist_name", "Unknown Artist")
        album_name = track.get("album_name") or "TopSpot40 Intro Tracks"
        add_metadata_to_mp3(out_path, track_name, artist_name, album_name)

        log_tts_action("Track Intro", track_id, out_path, "✅ Generated", play)
        generated.append(str(out_path))

    logger.info(f"✅ [Intro TTS] Generated {len(generated)} intro files")
    return {
        "message": f"✅ Generated {len(generated)} intro TTS files",
        "files": generated
    }
