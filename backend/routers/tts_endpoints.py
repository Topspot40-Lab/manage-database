from fastapi import APIRouter, Query
from pathlib import Path
import logging
import tempfile

from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

from backend.services.track_cache import get_all_rank_entries
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.services.supabase_storage import upload_bytes  # <-- uploads to Supabase
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.config import (
    BUCKETS, AUDIO_PREFIXES, DEFAULT_TTS_LANGUAGE,
    TTS_PROFILES,
    SKIP_TTS_IF_EXISTS,
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
)



import httpx

logger = logging.getLogger("tts_logger")

router = APIRouter(prefix="/tts", tags=["TTS"])

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
# Helpers (put near the other helpers)
def _canon_lang(lang: str) -> str:
    if not lang:
        return DEFAULT_TTS_LANGUAGE
    m = lang.strip()
    # normalize common inputs to your config keys
    if m.lower() == "pt-br":
        return "pt-BR"
    if m.lower() in {"en", "es"}:
        return m.lower()
    return DEFAULT_TTS_LANGUAGE


def _bucket_for(lang: str, kind: str) -> str:
    return (BUCKETS.get(lang) or BUCKETS[DEFAULT_TTS_LANGUAGE])[kind]

def _prefixed_key(kind: str, filename: str) -> str:
    return f"{AUDIO_PREFIXES[kind]}/{filename}"

def _voice_for(lang: str, kind: str) -> str:
    return TTS_PROFILES.get(lang, TTS_PROFILES[DEFAULT_TTS_LANGUAGE])[kind]["voice_id"]

async def _object_exists(bucket: str, key: str, client: httpx.AsyncClient) -> bool:
    url = f"{SUPABASE_URL}/storage/v1/object/info/{bucket}/{key}"
    headers = {"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "apikey": SUPABASE_SERVICE_ROLE_KEY}
    r = await client.get(url, headers=headers, timeout=5.0)
    return r.status_code == 200

def log_tts_action(context: str, identifier: str, dest: str, action: str, play: bool):
    logger.info(f"[{context}] {identifier}: {action} → {dest}")
    if play:
        logger.info(f"[{context}] 🔊 Playback triggered for: {dest}")
@router.post("/intro/by-rank")
async def generate_intro_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1),
    language: str = Query(DEFAULT_TTS_LANGUAGE),
    overwrite: bool = Query(False),
    play: bool = Query(False),
):
    logger.debug(f"🎙️ [Intro TTS] Requested ranks {start_rank}..{end_rank} | lang={language} | overwrite={overwrite} | play={play}")
    language = _canon_lang(language)

    if start_rank > end_rank:
        logger.warning("❌ [Intro TTS] Invalid range: start_rank > end_rank")
        return {"error": "Start rank must be <= end rank"}

    rankings = get_all_rank_entries()
    logger.debug(f"📋 [Intro TTS] Loaded {len(rankings)} track entries")

    intro_bucket = _bucket_for(language, "intro")
    intro_voice  = _voice_for(language, "intro")

    generated_objects = []

    async with httpx.AsyncClient() as client:
        for entry in rankings:
            rank = entry.get("rank")
            if rank is None or not (start_rank <= rank <= end_rank):
                continue

            intro_text = (entry.get("intro") or "").strip()
            if not intro_text:
                logger.debug(f"⚠️ [Intro TTS] No intro text for rank {rank}, skipping")
                continue

            decade = normalize_for_filename(entry.get("decade") or "unknown")
            genre  = normalize_for_filename(entry.get("genre") or "unknown")
            filename = f"{decade}_{genre}_{rank:02d}.mp3"
            key = _prefixed_key("intro", filename)

            if not overwrite and SKIP_TTS_IF_EXISTS and await _object_exists(intro_bucket, key, client):
                logger.debug(f"⏭️ [Intro TTS] Exists → skip {intro_bucket}/{key}")
                generated_objects.append(f"{intro_bucket}/{key}")
                continue

            # Synthesize to temp, tag, upload (with cleanup)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                generate_tts_mp3(intro_text, tmp_path, intro_voice, overwrite=True, play=play)

                track_name  = entry.get("track_name", "Unknown Track")
                artist_name = entry.get("artist_name", "Unknown Artist")
                album_name  = "TopSpot40 Intro Tracks"
                add_metadata_to_mp3(tmp_path, track_name, artist_name, album_name)

                upload_bytes(intro_bucket, key, tmp_path.read_bytes(), content_type="audio/mpeg")
                log_tts_action("Intro", f"rank:{rank}", f"{intro_bucket}/{key}", "✅ Uploaded", play)
                generated_objects.append(f"{intro_bucket}/{key}")
            finally:
                tmp_path.unlink(missing_ok=True)

    logger.info(f"✅ [Intro TTS] Generated/ensured {len(generated_objects)} object(s)")
    return {"message": f"✅ Generated {len(generated_objects)} intro TTS files", "objects": generated_objects}

@router.post("/generate-track-detail-tts-by-rank")
async def generate_track_detail_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1),
    language: str = Query(DEFAULT_TTS_LANGUAGE),
    overwrite: bool = Query(False),
    play: bool = Query(False),
):
    logger.debug(
        f"🎙️ [Track Detail TTS] ranks {start_rank}..{end_rank} | lang={language} | overwrite={overwrite} | play={play}")
    language = _canon_lang(language)

    if start_rank > end_rank:
        logger.warning("❌ [Track Detail TTS] Invalid range: start_rank > end_rank")
        return {"error": "Start rank must be <= end rank"}

    rankings = get_all_rank_entries()
    if not rankings:
        logger.warning("⚠️ [Track Detail TTS] No track data loaded.")
        return {"error": "No track data loaded. Load a JSON track file first."}

    detail_bucket = _bucket_for(language, "detail")
    detail_voice  = _voice_for(language, "detail")

    generated_objects = []

    async with httpx.AsyncClient() as client:
        for entry in rankings:
            rank = entry.get("rank")
            if rank is None or not (start_rank <= rank <= end_rank):
                continue

            detail = (entry.get("detail") or "").strip()
            if not detail:
                logger.debug(f"⚠️ [Track Detail TTS] No detail text for rank {rank}, skipping")
                continue

            track_id = entry.get("track_id") or entry.get("spotify_track_id")
            if not track_id:
                logger.warning(f"⚠️ [Track Detail TTS] Missing track ID for rank {rank}, skipping")
                continue

            key = _prefixed_key("detail", f"{track_id}.mp3")

            if not overwrite and SKIP_TTS_IF_EXISTS and await _object_exists(detail_bucket, key, client):
                logger.debug(f"⏭️ [Track Detail TTS] Exists → skip {detail_bucket}/{key}")
                generated_objects.append(f"{detail_bucket}/{key}")
                continue

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                generate_tts_mp3(detail, tmp_path, detail_voice, overwrite=True, play=play)

                track_name  = entry.get("track_name", "Unknown Track")
                artist_name = entry.get("artist_name", "Unknown Artist")
                album_name  = (entry.get("album_name")
                               or entry.get("spotify_data", {}).get("album_name")
                               or "Unknown Album")
                add_metadata_to_mp3(tmp_path, track_name, artist_name, album_name)

                upload_bytes(detail_bucket, key, tmp_path.read_bytes(), content_type="audio/mpeg")
                log_tts_action("TrackDetail", f"track:{track_id}", f"{detail_bucket}/{key}", "✅ Uploaded", play)
                generated_objects.append(f"{detail_bucket}/{key}")
            finally:
                tmp_path.unlink(missing_ok=True)

    logger.info(f"✅ [Track Detail TTS] Generated/ensured {len(generated_objects)} object(s)")
    return {"message": f"✅ Generated {len(generated_objects)} track detail TTS file(s)", "objects": generated_objects}

@router.post("/generate-all-track-detail-tts")  # (fixed path: no double /tts)
async def generate_all_track_detail_tts(
    language: str = Query(DEFAULT_TTS_LANGUAGE),
    overwrite: bool = Query(False),
    play: bool = Query(False),
):
    logger.debug(f"🎙️ [Track Detail TTS] Generate ALL | lang={language} | overwrite={overwrite} | play={play}")
    language = _canon_lang(language)
    rankings = get_all_rank_entries()
    detail_bucket = _bucket_for(language, "detail")
    detail_voice  = _voice_for(language, "detail")

    count = 0

    async with httpx.AsyncClient() as client:
        for entry in rankings:
            detail = (entry.get("detail") or "").strip()
            track_id = entry.get("track_id") or entry.get("spotify_track_id")
            if not detail or not track_id:
                continue

            key = _prefixed_key("detail", f"{track_id}.mp3")
            if not overwrite and SKIP_TTS_IF_EXISTS and await _object_exists(detail_bucket, key, client):
                continue

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                generate_tts_mp3(detail, tmp_path, detail_voice, overwrite=True, play=play)
                upload_bytes(detail_bucket, key, tmp_path.read_bytes(), content_type="audio/mpeg")
                count += 1
            finally:
                tmp_path.unlink(missing_ok=True)

    logger.info(f"✅ [Track Detail TTS] Generated/ensured {count} file(s)")
    return {"message": f"✅ Generated TTS for {count} tracks", "bucket": detail_bucket}

@router.post("/generate-all-artist-tts")  # (fixed path: no double /tts)
async def generate_all_artist_tts(
    language: str = Query(DEFAULT_TTS_LANGUAGE),
    overwrite: bool = Query(False),
    play: bool = Query(False),
):
    logger.debug(f"🎙️ [Artist TTS] Generate ALL | lang={language} | overwrite={overwrite} | play={play}")
    language = _canon_lang(language)
    rankings = get_all_rank_entries()
    artist_bucket = _bucket_for(language, "artist")
    artist_voice  = _voice_for(language, "artist")

    seen = set()
    count = 0

    async with httpx.AsyncClient() as client:
        for entry in rankings:
            artist_id   = entry.get("spotify_artist_id")
            artist_desc = (entry.get("artist_description") or "").strip()
            if not artist_id or not artist_desc or artist_id in seen:
                continue

            key = _prefixed_key("artist", f"{artist_id}.mp3")
            if not overwrite and SKIP_TTS_IF_EXISTS and await _object_exists(artist_bucket, key, client):
                seen.add(artist_id)
                continue

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                generate_tts_mp3(artist_desc, tmp_path, artist_voice, overwrite=True, play=play)

                artist_name = entry.get("artist_name", "Unknown Artist")
                track_name  = f"Artist Bio: {artist_name}"
                album_name  = "TopSpot40 Artist Bios"
                add_metadata_to_mp3(tmp_path, track_name, artist_name, album_name)

                upload_bytes(artist_bucket, key, tmp_path.read_bytes(), content_type="audio/mpeg")
                log_tts_action("Artist", f"artist:{artist_id}", f"{artist_bucket}/{key}", "✅ Uploaded", play)
                seen.add(artist_id)
                count += 1
            finally:
                tmp_path.unlink(missing_ok=True)

    logger.info(f"✅ [Artist TTS] Generated/ensured {count} unique artists")
    return {"message": f"✅ Generated TTS for {count} unique artists", "bucket": artist_bucket, "count": count}

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

# === ARTIST TTS ===
@router.get("/artist/list")
def list_unique_artists():
    """Returns a numbered list of unique artists with available descriptions."""

    rankings = get_all_rank_entries()

    seen = set()
    unique_artists = []
    for track in rankings:
        artist_id = track.get("spotify_artist_id")
        artist_name = track.get("artist_name", "Unknown Artist")
        artist_desc = track.get("artist_description", "").strip()

        if artist_id and artist_desc and artist_id not in seen:
            seen.add(artist_id)
            unique_artists.append({
                "index": len(unique_artists) + 1,
                "artist_id": artist_id,
                "artist_name": artist_name,
                "has_description": True
            })

    return {"total": len(unique_artists), "artists": unique_artists}

@router.post("/artist/by-range")
async def generate_artist_tts_range(
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
    language: str = Query(DEFAULT_TTS_LANGUAGE),
    overwrite: bool = Query(False),
    play: bool = Query(False),
):
    """Generate artist TTS for a specific range of unique artist indexes."""
    logger.debug(f"🎙️ [Artist TTS] Range {start}-{end} | lang={language} | overwrite={overwrite} | play={play}")
    language = _canon_lang(language)
    unique_artists = list_unique_artists()["artists"]
    selected = unique_artists[start - 1:end]  # 1-based indexing

    rankings = get_all_rank_entries()
    artist_lookup = {
        track.get("spotify_artist_id"): track
        for track in rankings
        if track.get("spotify_artist_id") and track.get("artist_description")
    }

    artist_bucket = _bucket_for(language, "artist")
    artist_voice  = _voice_for(language, "artist")

    generated = []

    async with httpx.AsyncClient() as client:
        for artist in selected:
            artist_id = artist["artist_id"]
            track = artist_lookup.get(artist_id)
            if not track:
                logger.debug(f"⚠️ [Artist TTS] No valid track found for artist_id: {artist_id}, skipping")
                continue

            artist_name = artist["artist_name"]
            artist_desc = (track["artist_description"] or "").strip()

            key = _prefixed_key("artist", f"{artist_id}.mp3")
            if not overwrite and SKIP_TTS_IF_EXISTS and await _object_exists(artist_bucket, key, client):
                log_tts_action("Artist", artist_id, f"{artist_bucket}/{key}", "⏭️ Skipped (exists)", play)
                generated.append(f"{artist_bucket}/{key}")
                continue

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                generate_tts_mp3(artist_desc, tmp_path, artist_voice, overwrite=True, play=play)

                track_name = f"Artist Bio: {artist_name}"
                album_name = "TopSpot40 Artist Bios"
                add_metadata_to_mp3(tmp_path, track_name, artist_name, album_name)

                upload_bytes(artist_bucket, key, tmp_path.read_bytes(), content_type="audio/mpeg")
                log_tts_action("Artist", artist_id, f"{artist_bucket}/{key}", "✅ Uploaded", play)
                generated.append(f"{artist_bucket}/{key}")
            finally:
                tmp_path.unlink(missing_ok=True)

    logger.info(f"✅ [Artist TTS] Generated/ensured {len(generated)} artists in range {start}-{end}")
    return {"message": f"✅ Generated {len(generated)} artist TTS files in range {start}-{end}", "objects": generated}

@router.post("/artist/by-description-range")
async def generate_artist_tts_descriptions(
    start_index: int = Query(..., ge=1),
    end_index: int = Query(..., ge=1),
    language: str = Query(DEFAULT_TTS_LANGUAGE),
    overwrite: bool = Query(False),
    play: bool = Query(False),
):
    language = _canon_lang(language)
    rankings = get_all_rank_entries()

    seen = {}
    for track in rankings:
        aid = track.get("spotify_artist_id")
        if aid and track.get("artist_description") and aid not in seen:
            seen[aid] = track

    unique_tracks = list(seen.values())
    selected = unique_tracks[start_index - 1:end_index]

    artist_bucket = _bucket_for(language, "artist")
    artist_voice  = _voice_for(language, "artist")

    generated = []

    async with httpx.AsyncClient() as client:
        for track in selected:
            artist_id   = track.get("spotify_artist_id")
            artist_name = track.get("artist_name", "Unknown Artist")
            artist_desc = (track.get("artist_description") or "").strip()
            if not artist_id or not artist_desc:
                continue

            key = _prefixed_key("artist", f"{artist_id}.mp3")
            if not overwrite and SKIP_TTS_IF_EXISTS and await _object_exists(artist_bucket, key, client):
                log_tts_action("Artist", artist_id, f"{artist_bucket}/{key}", "⏭️ Skipped (exists)", play)
                generated.append(f"{artist_bucket}/{key}")
                continue

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                generate_tts_mp3(artist_desc, tmp_path, artist_voice, overwrite=True, play=play)

                track_name = f"Artist Bio: {artist_name}"
                album_name = "TopSpot40 Artist Bios"
                add_metadata_to_mp3(tmp_path, track_name, artist_name, album_name)

                upload_bytes(artist_bucket, key, tmp_path.read_bytes(), content_type="audio/mpeg")
                log_tts_action("Artist", artist_id, f"{artist_bucket}/{key}", "✅ Uploaded", play)
                generated.append(f"{artist_bucket}/{key}")
            finally:
                tmp_path.unlink(missing_ok=True)

    return {"message": f"✅ Generated {len(generated)} artist TTS files", "objects": generated}
