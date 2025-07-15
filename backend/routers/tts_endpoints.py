from fastapi import APIRouter, Query
from pathlib import Path
from backend.services.track_cache import get_all_rankings
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_INTRO
import logging
logger = logging.getLogger("tts_logger")


def log_tts_action(context: str, identifier: str, path: Path, action: str, play: bool):
    logger.info(f"[{context}] {identifier}: {action} → {path}")
    if play:
        logger.info(f"[{context}] 🔊 Playback triggered for: {path}")

router = APIRouter()

@router.post("/tts/generate-intro-tts-by-rank")
def generate_intro_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1)
):
    if start_rank > end_rank:
        return {"error": "Start rank must be <= end rank"}

    rankings = get_all_rankings()
    output_dir = Path("data/mp3_files/intro_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []

    for entry in rankings:
        rank = entry.get("rank")
        if rank is None or not (start_rank <= rank <= end_rank):
            continue

        intro_text = entry.get("intro")
        decade = entry.get("decade", "unknown").replace(" ", "_").lower()
        genre = entry.get("genre", "unknown").replace(" ", "_").lower()

        if not intro_text:
            continue

        filename = f"{decade}_{genre}_{rank:02d}.mp3"
        out_path = output_dir / filename

        generate_tts_mp3(intro_text, out_path, VOICE_ID_INTRO, overwrite=True)
        generated_files.append(str(out_path))

    return {
        "message": f"✅ Generated {len(generated_files)} intro TTS files",
        "files": generated_files
    }
@router.get("/tts/generate-track-detail-tts-by-rank")
def generate_track_detail_tts_by_rank(
    rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    rankings = get_all_rankings()
    match = next((t for t in rankings if t.get("rank") == rank), None)
    if not match:
        return {"error": f"No track found with rank {rank}"}

    intro = match.get("intro", "").strip()
    detail = match.get("detail", "").strip()

    if not intro and not detail:
        return {"error": "No intro or detail available for TTS."}

    track_id = match.get("spotify_track_id")
    if not track_id:
        return {"error": "Missing spotify_track_id for filename generation."}

    full_text = f"{intro} {detail}".strip()
    out_path = Path("data/mp3_files/track_detail_mp3_files") / f"{track_id}.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not overwrite:
        log_tts_action("Track", track_id, out_path, "⏭️ Skipped (exists)", play)
    else:
        generate_tts_mp3(full_text, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)
        log_tts_action("Track", track_id, out_path, "✅ Generated", play)

    return {
        "message": f"✅ Track detail TTS generated for rank {rank}",
        "file": str(out_path)
    }

@router.get("/tts/generate-artist-tts-by-rank")
def generate_artist_tts_by_rank(
    rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    rankings = get_all_rankings()
    match = next((t for t in rankings if t.get("rank") == rank), None)
    if not match:
        return {"error": f"No track found with rank {rank}"}

    artist_desc = match.get("artist_description", "").strip()
    if not artist_desc:
        return {"error": "No artist description available for TTS."}

    artist_id = match.get("spotify_artist_id")
    if not artist_id:
        return {"error": "Missing spotify_artist_id for filename generation."}

    out_path = Path("data/mp3_files/artist_mp3_files") / f"{artist_id}.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not overwrite:
        log_tts_action("Artist", artist_id, out_path, "⏭️ Skipped (exists)", play)
    else:
        generate_tts_mp3(artist_desc, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)
        log_tts_action("Artist", artist_id, out_path, "✅ Generated", play)

    return {
        "message": f"✅ Artist TTS generated for rank {rank}",
        "file": str(out_path)
    }

@router.post("/tts/generate-all-track-detail-tts")
def generate_all_track_detail_tts(
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    rankings = get_all_rankings()
    out_dir = Path("data/mp3_files/track_detail_mp3_files")
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for track in rankings:
        intro = track.get("intro", "").strip()
        detail = track.get("detail", "").strip()
        if not intro and not detail:
            continue

        track_id = track.get("spotify_track_id")
        if not track_id:
            continue

        out_path = out_dir / f"{track_id}.mp3"
        if out_path.exists() and not overwrite:
            continue

        full_text = f"{intro} {detail}".strip()
        generate_tts_mp3(full_text, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)
        count += 1

    return {"message": f"✅ Generated TTS for {count} tracks"}

@router.post("/tts/generate-all-artist-tts")
def generate_all_artist_tts(
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    rankings = get_all_rankings()
    out_dir = Path("data/mp3_files/artist_mp3_files")
    out_dir.mkdir(parents=True, exist_ok=True)

    seen = set()
    count = 0

    for track in rankings:
        artist_id = track.get("spotify_artist_id")
        artist_desc = track.get("artist_description", "").strip()
        if not artist_id or not artist_desc or artist_id in seen:
            continue

        out_path = out_dir / f"{artist_id}.mp3"

        if out_path.exists() and not overwrite:
            log_tts_action("Artist", artist_id, out_path, "⏭️ Skipped (exists)", play)
            seen.add(artist_id)
            continue

        generate_tts_mp3(artist_desc, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)
        log_tts_action("Artist", artist_id, out_path, "✅ Generated", play)
        seen.add(artist_id)
        count += 1

    return {
        "message": f"✅ Generated TTS for {count} unique artists",
        "generated_count": count
    }
