from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from sqlmodel import Session, select

from backend.services.ads.script_generator import (
    TrackAdInputs, generate_ad_script
)
from backend.models.dbmodels import (
    Track, Artist, TrackRanking, DecadeGenre, Decade, Genre
)

# TTS + storage (both optional—fail soft if missing)
try:
    from backend.services.elevenlabs_tts import synth_to_mp3_bytes  # (text, *, voice_id=None, model_id=None, voice_settings=None, speed=None)
    HAS_TTS = True
except Exception:
    HAS_TTS = False

try:
    from backend.services.supabase_storage import upload_bytes
    HAS_SUPABASE = True
except Exception:
    HAS_SUPABASE = False

log = logging.getLogger("backend.services.ads.ad_audio")
ADS_DIR = Path("data/mp3_files/ads_mp3_files")
ADS_DIR.mkdir(parents=True, exist_ok=True)

def _load_context_by_track(db: Session, track_id: int):
    stmt = (
        select(Track, Artist, TrackRanking, DecadeGenre, Decade, Genre)
        .join(Artist, Artist.id == Track.artist_id, isouter=True)
        .join(TrackRanking, TrackRanking.track_id == Track.id, isouter=True)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id, isouter=True)
        .join(Decade, Decade.id == DecadeGenre.decade_id, isouter=True)
        .join(Genre, Genre.id == DecadeGenre.genre_id, isouter=True)
        .where(Track.id == track_id)
        .limit(1)
    )
    row = db.exec(stmt).first()
    if not row:
        raise ValueError(f"Track {track_id} not found")
    return row  # (track, artist, ranking, dg, decade, genre)

def _make_inputs(track, artist, ranking, decade, genre, language: str) -> TrackAdInputs:
    title = getattr(track, "title", None) or getattr(track, "name", "(untitled)")
    artist_name = getattr(artist, "name", None) or "Unknown Artist"
    year = getattr(track, "release_year", None) or getattr(track, "year", None)
    intro = getattr(ranking, "intro", None) if ranking else None
    detail = getattr(ranking, "detail", None) if ranking else None
    category = getattr(decade, "name", None) if decade else None
    genre_name = getattr(genre, "name", None) if genre else None
    rank = getattr(ranking, "rank", None) if ranking else None

    return TrackAdInputs(
        track_title=title,
        artist_name=artist_name,
        year_released=str(year) if year is not None else None,
        category=category,
        genre=genre_name,
        intro_text=intro,
        detail_text=detail,
        rank=rank,
        language=language,
    )

def build_ad_script_and_mp3_by_track(
    db: Session,
    *,
    track_id: int,
    language: str = "en",
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    speed: Optional[float] = None,
    upload: bool = False,
    bucket: Optional[str] = None,
    key_prefix: str = "ads/",
) -> Dict[str, Any]:
    """
    Returns:
      {
        "script": str,
        "estimated_seconds": int,
        "notes": str,
        "local_mp3": "data/mp3_files/ads_mp3_files/....mp3",
        "uploaded": {"bucket": ..., "key": ...} | None
      }
    """
    track, artist, ranking, dg, decade, genre = _load_context_by_track(db, track_id)
    inputs = _make_inputs(track, artist, ranking, decade, genre, language)
    script_payload = generate_ad_script(inputs)

    script = script_payload["script"]
    secs = int(script_payload["estimated_seconds"])
    if secs > 33:
        log.warning("Ad script ~%ss > 30s target (track_id=%s). Consider trimming detail.", secs, track_id)

    # Synthesize
    if not HAS_TTS:
        raise RuntimeError("ElevenLabs TTS integration not available")

    mp3_bytes = synth_to_mp3_bytes(
        script,
        voice_id=voice_id,
        model_id=model_id,
        speed=speed,
    )

    # Save locally (mp3 + txt)
    safe_lang = language.replace("/", "_")
    fname_base = f"ad_track_{track_id}_{safe_lang}"
    mp3_path = ADS_DIR / f"{fname_base}.mp3"
    txt_path = ADS_DIR / f"{fname_base}.txt"

    mp3_path.write_bytes(mp3_bytes)
    txt_path.write_text(script, encoding="utf-8")

    uploaded = None
    if upload:
        if not HAS_SUPABASE:
            log.error("Upload requested but Supabase not configured")
        else:
            # conservative default bucket
            bucket_name = bucket or "ads-mp3-files"
            key = f"{key_prefix}{mp3_path.name}"
            try:
                upload_bytes(bucket_name, key, mp3_bytes, content_type="audio/mpeg")
                uploaded = {"bucket": bucket_name, "key": key}
            except Exception as e:
                log.exception("Upload failed to %s/%s", bucket_name, key)

    return {
        "script": script,
        "estimated_seconds": secs,
        "notes": script_payload.get("notes", ""),
        "local_mp3": str(mp3_path),
        "local_txt": str(txt_path),
        "uploaded": uploaded,
    }
