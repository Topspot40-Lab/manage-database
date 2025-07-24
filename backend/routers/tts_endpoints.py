from fastapi import APIRouter, Query
from pathlib import Path
from backend.services.track_cache import get_all_rank_entries
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_INTRO, VOICE_ID_TRACK, VOICE_ID_ARTIST
import logging
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3



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
    logger.debug(f"🎙️ [Intro TTS] Requested ranks {start_rank} to {end_rank}")

    if start_rank > end_rank:
        logger.warning("❌ [Intro TTS] Invalid range: start_rank > end_rank")
        return {"error": "Start rank must be <= end rank"}

    rankings = get_all_rank_entries()
    logger.debug(f"📋 [Intro TTS] Loaded {len(rankings)} track entries")

    output_dir = Path("data/mp3_files/intro_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []

    for entry in rankings:
        rank = entry.get("rank")
        if rank is None or not (start_rank <= rank <= end_rank):
            continue

        intro_text = entry.get("intro")
        if not intro_text:
            logger.debug(f"⚠️ [Intro TTS] No intro text for rank {rank}, skipping")
            continue

        decade = entry.get("decade", "unknown").replace(" ", "_").lower()
        genre = entry.get("genre", "unknown").replace(" ", "_").lower()
        filename = f"{decade}_{genre}_{rank:02d}.mp3"
        out_path = output_dir / filename

        logger.debug(f"🎧 [Intro TTS] Generating MP3: {out_path}")
        generate_tts_mp3(intro_text, out_path, VOICE_ID_INTRO, overwrite=True)
        generated_files.append(str(out_path))

    logger.info(f"✅ [Intro TTS] Generated {len(generated_files)} files")
    return {
        "message": f"✅ Generated {len(generated_files)} intro TTS files",
        "files": generated_files
    }
@router.post("/tts/generate-track-detail-tts-by-rank")
def generate_track_detail_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    logger.debug(f"🎙️ [Track Detail TTS] Requested ranks {start_rank} to {end_rank} | overwrite={overwrite} | play={play}")

    if start_rank > end_rank:
        logger.warning("❌ [Track Detail TTS] Invalid range: start_rank > end_rank")
        return {"error": "Start rank must be <= end rank"}

    rankings = get_all_rank_entries()
    if not rankings:
        logger.warning(
            "⚠️ [Track Detail TTS] No track data loaded. Did you forget to call /json/load-json-track-file first?")
        return {
            "error": "No track data loaded. Please load a JSON track file first using /json/load-json-track-file?genre=...&decade=..."
        }

    logger.debug(f"📋 [Track Detail TTS] Loaded {len(rankings)} track entries")

    output_dir = Path("data/mp3_files/track_detail_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []

    for entry in rankings:
        rank = entry.get("rank")
        # logger.debug(f"🔍 Full entry for rank {rank}: {entry}")

        if rank is None or not (start_rank <= rank <= end_rank):
            continue

        detail = entry.get("detail", "").strip()
        logger.debug(f"🔍 Detail Field {detail}")
        if not detail:
            logger.debug(f"⚠️ [Track Detail TTS] No detail text for rank {rank}, skipping")
            continue

        track_id = entry.get("track_id")
        if not track_id:
            logger.warning(f"⚠️ [Track Detail TTS] Missing track ID for rank {rank}, skipping")
            continue

        # full_text = f"{intro} {detail}".strip()
        # Only want detail text here, intro text separate
        full_text = f"{detail}".strip()
        out_path = output_dir / f"{track_id}.mp3"

        if out_path.exists() and not overwrite:
            logger.debug(f"⏭️ [Track Detail TTS] File exists, skipping: {out_path}")
            log_tts_action("Track", track_id, out_path, "⏭️ Skipped (exists)", play)
        else:
            logger.debug(f"🎧 [Track Detail TTS] Generating MP3: {out_path}")
            generate_tts_mp3(full_text, out_path, VOICE_ID_TRACK, overwrite=overwrite, play=play)
            # Add metadata from ranking entry
            track_name = entry.get("track_name", "Unknown Track")
            artist_name = entry.get("artist_name", "Unknown Artist")
            album_name = entry.get("album_name", "Unknown Album")

            add_metadata_to_mp3(out_path, track_name, artist_name, album_name)


            log_tts_action("Track", track_id, out_path, "✅ Generated", play)

        generated_files.append(str(out_path))

    logger.info(f"✅ [Track Detail TTS] Generated {len(generated_files)} files")
    return {
        "message": f"✅ Generated {len(generated_files)} track detail TTS file(s)",
        "files": generated_files
    }

@router.get("/tts/generate-artist-tts-by-rank")
def generate_artist_tts_by_rank(
    rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    rankings = get_all_rank_entries()
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
        generate_tts_mp3(artist_desc, out_path, VOICE_ID_ARTIST, overwrite=overwrite, play=play)
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
    logger.debug(f"🎙️ [Track Detail TTS] Generating all tracks | overwrite={overwrite} | play={play}")

    rankings = get_all_rank_entries()
    logger.debug(f"📋 [Track Detail TTS] Loaded {len(rankings)} track entries")

    out_dir = Path("data/mp3_files/track_detail_mp3_files")
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for track in rankings:
        intro = track.get("intro", "").strip()
        detail = track.get("detail", "").strip()
        if not intro and not detail:
            logger.debug(f"⚠️ [Track Detail TTS] No text for track {track.get('rank', 'unknown')}, skipping")
            continue

        track_id = track.get("spotify_track_id")
        if not track_id:
            logger.warning(f"⚠️ [Track Detail TTS] Missing track ID for rank {track.get('rank', 'unknown')}, skipping")
            continue

        out_path = out_dir / f"{track_id}.mp3"
        if out_path.exists() and not overwrite:
            logger.debug(f"⏭️ [Track Detail TTS] Skipping existing file: {out_path}")
            continue

        full_text = f"{intro} {detail}".strip()
        logger.debug(f"🎧 [Track Detail TTS] Generating MP3: {out_path}")
        generate_tts_mp3(full_text, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)
        count += 1

    logger.info(f"✅ [Track Detail TTS] Generated TTS for {count} tracks")
    return {"message": f"✅ Generated TTS for {count} tracks"}
@router.post("/tts/generate-all-artist-tts")
def generate_all_artist_tts(
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    logger.debug(f"🎙️ [Artist TTS] Generating all artist files | overwrite={overwrite} | play={play}")

    rankings = get_all_rank_entries()
    logger.debug(f"📋 [Artist TTS] Loaded {len(rankings)} track entries")

    out_dir = Path("data/mp3_files/artist_mp3_files")
    out_dir.mkdir(parents=True, exist_ok=True)

    seen = set()
    count = 0

    for track in rankings:
        artist_id = track.get("spotify_artist_id")
        artist_desc = track.get("artist_description", "").strip()
        rank = track.get("rank", "unknown")

        if not artist_id or not artist_desc:
            logger.debug(f"⚠️ [Artist TTS] Skipping rank {rank}: Missing artist_id or description")
            continue
        if artist_id in seen:
            logger.debug(f"🔁 [Artist TTS] Already processed: {artist_id}")
            continue

        out_path = out_dir / f"{artist_id}.mp3"

        if out_path.exists() and not overwrite:
            logger.debug(f"⏭️ [Artist TTS] File exists, skipping: {out_path}")
            log_tts_action("Artist", artist_id, out_path, "⏭️ Skipped (exists)", play)
            seen.add(artist_id)
            continue

        logger.debug(f"🎧 [Artist TTS] Generating MP3 for artist_id {artist_id}")
        generate_tts_mp3(artist_desc, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)
        log_tts_action("Artist", artist_id, out_path, "✅ Generated", play)
        seen.add(artist_id)
        count += 1

    logger.info(f"✅ [Artist TTS] Generated TTS for {count} unique artists")
    return {
        "message": f"✅ Generated TTS for {count} unique artists",
        "generated_count": count
    }
def add_metadata_to_mp3(mp3_path: Path, track_name: str, artist_name: str, album_name: str):
    try:
        audio = MP3(mp3_path, ID3=EasyID3)
        audio["title"] = track_name
        audio["artist"] = artist_name
        audio["album"] = album_name
        audio.save()
        logger.debug(
            f"🔖 [TTS Metadata] Tagged '{mp3_path.name}' → Title: '{track_name}' | Artist: '{artist_name}' | Album: '{album_name}'"
        )
    except Exception as e:
        logger.warning(f"❌ [TTS Metadata] Failed to tag {mp3_path.name}: {e}")
