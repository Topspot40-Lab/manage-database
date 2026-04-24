from fastapi import APIRouter, Query, Depends
import logging
import tempfile
from pathlib import Path

from sqlmodel import Session, select

from backend.database import get_db
from backend.models.dbmodels import TrackLocale
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.services.supabase_storage import upload_bytes
from backend.models.dbmodels import TrackLocale, Track
from backend.config.tts import (
    TTS_PROFILES,
    DEFAULT_TTS_LANGUAGE,
    SKIP_TTS_IF_EXISTS,
)

logger = logging.getLogger("tts_new")

router = APIRouter(prefix="/tts-new", tags=["TTS New"])


def _canon_lang(lang: str) -> str:
    """Normalize incoming language values to the keys used in TTS_PROFILES/DB."""
    if not lang:
        return DEFAULT_TTS_LANGUAGE

    cleaned = lang.strip().lower()

    if cleaned in {"pt-br", "ptbr", "pt_br"}:
        return "ptbr"
    if cleaned in {"en", "es"}:
        return cleaned

    return DEFAULT_TTS_LANGUAGE


def _tts_profile(lang: str, kind: str) -> dict:
    """Return the TTS profile for a given language/kind, falling back to default."""
    profiles = TTS_PROFILES.get(lang, TTS_PROFILES[DEFAULT_TTS_LANGUAGE])
    return profiles[kind]


def _voice(lang: str, kind: str) -> str:
    return _tts_profile(lang, kind)["voice_id"]


def _settings(lang: str, kind: str) -> dict:
    return _tts_profile(lang, kind)["settings"]


def _bucket_for(lang: str) -> str:
    return {
        "en": "audio-en",
        "es": "audio-es",
        "ptbr": "audio-ptbr",
    }.get(lang, "audio-en")


@router.post("/generate-detail-from-track-locale")
async def generate_detail_from_track_locale(
    language: str = Query("es"),
    limit: int | None = Query(None, ge=1),
    overwrite: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Generate detail MP3 files from public.track_locale.detail_text.

    Reads rows from TrackLocale where:
      - language_code == requested language
      - detail_text is not null

    Uploads files to:
      bucket/detail/<track_id>.mp3

    Updates the same TrackLocale row with:
      - tts_bucket
      - tts_key
    """
    language = _canon_lang(language)
    bucket = _bucket_for(language)
    voice_id = _voice(language, "detail")

    stmt = (
        select(TrackLocale, Track)
        .join(Track, Track.id == TrackLocale.track_id)
        .where(TrackLocale.language_code == language)
        .where(TrackLocale.detail_text.is_not(None))  # type: ignore
    )

    rows = db.exec(stmt).all()

    if limit:
        rows = rows[:limit]

    if not rows:
        return {
            "message": "No matching track_locale rows found",
            "language": language,
            "bucket": bucket,
        }

    generated = []
    skipped = 0
    errors = []

    for row, track in rows:
        detail_text = (row.detail_text or "").strip()
        spotify_track_id = (track.spotify_track_id or "").strip()

        if not detail_text or not spotify_track_id:
            skipped += 1
            continue

        key = f"detail/{spotify_track_id}.mp3"

        # Skip if already recorded in DB and overwrite is False
        if (
            not overwrite
            and SKIP_TTS_IF_EXISTS
            and row.tts_bucket == bucket
            and row.tts_key == key
        ):
            skipped += 1
            logger.info(f"⏭️ Skipping existing DB-linked file: {bucket}/{key}")
            continue

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # NOTE:
            # This assumes your generate_tts_mp3() supports the parameters below,
            # including `settings=...`.
            generate_tts_mp3(
                text=detail_text,
                out_path=tmp_path,
                voice_id=voice_id,
                overwrite=True,
                play=False,
                settings=_tts_profile(language, "detail")["settings"],
                language=language,
            )

            upload_bytes(
                bucket,
                key,
                tmp_path.read_bytes(),
                content_type="audio/mpeg",
            )

            row.tts_bucket = bucket
            row.tts_key = key
            db.add(row)

            generated.append(
                {
                    "track_locale_id": row.id,
                    "track_id": row.track_id,
                    "spotify_track_id": spotify_track_id,
                    "bucket": bucket,
                    "key": key,
                }
            )
            logger.info(f"✅ Uploaded {bucket}/{key}")

        except Exception as exc:
            logger.exception(
                f"❌ Failed generating/uploading row_track_id={row.track_id} spotify_track_id={spotify_track_id}"
            )
            errors.append(
                {
                    "track_locale_id": getattr(row, "id", None),
                    "track_id": row.track_id,
                    "spotify_track_id": spotify_track_id,
                    "error": str(exc),
                }
            )

        finally:
            tmp_path.unlink(missing_ok=True)

    db.commit()

    return {
        "message": f"Generated {len(generated)} detail TTS files",
        "language": language,
        "bucket": bucket,
        "voice_id": voice_id,
        "generated_count": len(generated),
        "skipped_count": skipped,
        "error_count": len(errors),
        "generated": generated,
        "errors": errors,
    }