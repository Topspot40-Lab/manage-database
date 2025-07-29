from fastapi import APIRouter, Query
from pathlib import Path
import logging

from backend.services.track_cache import get_all_rank_entries
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_TRACK
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action

logger = logging.getLogger("tts_logger")

# === Track Detail TTS ===
detail_router = APIRouter(
    prefix="/tts/detail",
    tags=["TTS - Track Detail"]
)

@detail_router.post("/by-rank")
def generate_track_detail_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    """
    Generate TTS for the 'detail' field of ranked tracks in the specified range.
    """
    logger.debug(f"🎙️ [Track Detail TTS] Requested ranks {start_rank} to {end_rank} | overwrite={overwrite} | play={play}")

    if start_rank > end_rank:
        return {"error": "Start rank must be less than or equal to end rank."}

    rankings = get_all_rank_entries()
    output_dir = Path("data/mp3_files/track_detail_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for track in rankings:
        rank = track.get("rank")
        if not rank or not (start_rank <= rank <= end_rank):
            continue

        detail = track.get("detail", "").strip()
        if not detail:
            continue

        track_id = track.get("spotify_track_id")
        if not track_id:
            continue

        out_path = output_dir / f"{track_id}.mp3"

        if out_path.exists() and not overwrite:
            log_tts_action("Track Detail", track_id, out_path, "⏭️ Skipped (exists)", play)
            continue

        generate_tts_mp3(detail, out_path, VOICE_ID_TRACK, overwrite=overwrite, play=play)

        track_name = track.get("track_name", "Unknown Track")
        artist_name = track.get("artist_name", "Unknown Artist")
        album_name = track.get("album_name") or "TopSpot40 Detail Tracks"
        add_metadata_to_mp3(out_path, track_name, artist_name, album_name)

        log_tts_action("Track Detail", track_id, out_path, "✅ Generated", play)
        generated.append(str(out_path))

    logger.info(f"✅ [Track Detail TTS] Generated {len(generated)} detail files")
    return {
        "message": f"✅ Generated {len(generated)} track detail TTS files",
        "files": generated
    }
