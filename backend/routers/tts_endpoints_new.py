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
        track_id: int | None = Query(None),
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
    db_language = "pt-BR" if language == "ptbr" else language
    bucket = _bucket_for(language)
    voice_id = _voice(language, "detail")

    stmt = (
        select(TrackLocale, Track)
        .join(Track, Track.id == TrackLocale.track_id)
        .where(TrackLocale.language_code == db_language)
        .where(TrackLocale.detail_text.is_not(None))  # type: ignore
    )

    if track_id is not None:
        stmt = stmt.where(TrackLocale.track_id == track_id)

    if not overwrite:
        stmt = stmt.where(
            (TrackLocale.tts_key.is_(None)) | (TrackLocale.tts_bucket.is_(None))  # type: ignore
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

        if not detail_text:
            skipped += 1
            continue

        key_id = spotify_track_id if spotify_track_id else str(row.track_id)
        key = f"detail/{key_id}.mp3"

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


@router.post("/generate-detail-from-track")
async def generate_detail_from_track(
        overwrite: bool = Query(False),
        db: Session = Depends(get_db),
):
    bucket = "audio-en"
    language = "en"
    voice_id = _voice(language, "detail")

    # 🔥 Only the 88 missing tracks
    missing_ids = [
        3936, 3937, 3935, 3939, 3940, 3941, 3942, 3943, 3944, 3945,
        3946, 3947, 3949, 3952, 3953, 3954, 3955, 3956, 3958, 3961,
        3964, 3966, 3969, 3972, 3948, 3950, 3951, 3957, 3959, 3960,
        3962, 3963, 3965, 3967, 3968, 3970, 3971, 3973, 3974, 3975,
        3976, 3977, 3978, 3979, 3980, 3981, 3982, 3983, 3984, 3985,
        3986, 3987, 3988, 3989, 3990, 3991, 3992, 3993, 3994, 3995,
        3996, 3997, 3998, 3999, 4000, 4001, 4002, 4003, 4004, 4005,
        4006, 4007, 4008, 4009, 4010, 4011, 4012, 4014, 4015, 4016,
        4017, 4018, 4019, 4020, 4021, 4022, 4023, 4024, 4025, 4026,
        4027, 4028, 4029, 4030, 4031, 4032, 4033, 4034, 4035, 4036
    ]

    stmt = select(Track).where(Track.id.in_(missing_ids))
    tracks = db.exec(stmt).all()

    generated = []
    skipped = 0

    for track in tracks:
        detail_text = (track.detail or "").strip()
        spotify_track_id = (track.spotify_track_id or "").strip()

        if not detail_text or not spotify_track_id:
            skipped += 1
            continue

        key = f"detail/{spotify_track_id}.mp3"

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            generate_tts_mp3(
                text=detail_text,
                out_path=tmp_path,
                voice_id=voice_id,
                overwrite=True,
                play=False,
                settings=_settings(language, "detail"),
                language=language,
            )

            upload_bytes(
                bucket,
                key,
                tmp_path.read_bytes(),
                content_type="audio/mpeg",
            )

            generated.append({
                "track_id": track.id,
                "spotify_track_id": spotify_track_id,
                "key": key,
            })

            logger.info(f"✅ Uploaded {bucket}/{key}")

        except Exception as exc:
            logger.exception(f"❌ Failed track_id={track.id}")

        finally:
            tmp_path.unlink(missing_ok=True)

    return {
        "generated_count": len(generated),
        "skipped_count": skipped,
        "generated": generated,
    }


from backend.models.dbmodels import ArtistLocale, Artist


@router.post("/generate-artist-from-locale")
async def generate_artist_from_locale(
        language: str = Query("es"),
        limit: int | None = Query(None, ge=1),
        overwrite: bool = Query(False),
        db: Session = Depends(get_db),
):
    language = _canon_lang(language)
    db_language = "pt-BR" if language == "ptbr" else language
    bucket = _bucket_for(language)
    voice_id = _voice(language, "artist")

    stmt = (
        select(ArtistLocale, Artist)
        .join(Artist, Artist.id == ArtistLocale.artist_id)
        .where(ArtistLocale.language_code == db_language)
        .where(ArtistLocale.artist_description_text.is_not(None))
    )

    rows = db.exec(stmt).all()

    if limit:
        rows = rows[:limit]

    if not rows:
        return {
            "message": "No matching artist_locale rows found",
            "language": language,
            "bucket": bucket,
        }

    generated = []
    skipped = 0
    errors = []

    for row, artist in rows:
        text = (row.artist_description_text or "").strip()
        spotify_artist_id = (artist.spotify_artist_id or "").strip()

        if not text:
            skipped += 1
            continue

        key = (
            f"artist/{spotify_artist_id}.mp3"
            if spotify_artist_id
            else f"artist/{artist.id}.mp3"
        )

        if (
                not overwrite
                and SKIP_TTS_IF_EXISTS
                and row.tts_bucket == bucket
                and row.tts_key == key
        ):
            skipped += 1
            continue

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            generate_tts_mp3(
                text=text,
                out_path=tmp_path,
                voice_id=voice_id,
                overwrite=True,
                play=False,
                settings=_settings(language, "artist"),
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

            generated.append({
                "artist_locale_id": row.id,
                "artist_id": row.artist_id,
                "spotify_artist_id": spotify_artist_id,
                "bucket": bucket,
                "key": key,
            })

        except Exception as exc:
            logger.exception(f"❌ Failed artist_id={row.artist_id}")
            errors.append({
                "artist_id": row.artist_id,
                "spotify_artist_id": spotify_artist_id,
                "error": str(exc),
            })

        finally:
            tmp_path.unlink(missing_ok=True)

    db.commit()

    return {
        "message": f"Generated {len(generated)} artist TTS files",
        "language": language,
        "bucket": bucket,
        "generated_count": len(generated),
        "skipped_count": skipped,
        "error_count": len(errors),
        "generated": generated,
        "errors": errors,
    }
