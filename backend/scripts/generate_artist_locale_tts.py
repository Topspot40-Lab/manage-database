import argparse
import logging
import tempfile
import time
from pathlib import Path

from sqlmodel import Session, select

from backend.database import engine
from backend.models.dbmodels import ArtistLocale
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.services.supabase_storage import upload_bytes
from backend.config.tts import TTS_PROFILES, DEFAULT_TTS_LANGUAGE
from backend.services.tts_prep import prepare_for_tts_es, prepare_for_tts_pt_br
from backend.models.dbmodels import Artist


logger = logging.getLogger("artist_locale_tts")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BATCH_SIZE = 50
PAUSE_BETWEEN_REQUESTS_SEC = 0.3
PAUSE_BETWEEN_BATCHES_SEC = 2.0


def _canon_lang(language: str) -> str:
    if not language:
        return DEFAULT_TTS_LANGUAGE

    cleaned = language.strip().lower()

    if cleaned in {"ptbr", "pt-br", "pt_br"}:
        return "ptbr"
    if cleaned in {"es", "en"}:
        return cleaned

    return DEFAULT_TTS_LANGUAGE


def _bucket_for(language: str) -> str:
    return {
        "en": "audio-en",
        "es": "audio-es",
        "ptbr": "audio-ptbr",
    }.get(language, "audio-en")


def _voice_for(language: str, kind: str = "artist") -> str:
    profiles = TTS_PROFILES.get(language, TTS_PROFILES[DEFAULT_TTS_LANGUAGE])
    profile = profiles.get(kind, {})
    voice_id = profile.get("voice_id")
    if not voice_id:
        raise ValueError(f"No voice_id configured for language={language}, kind={kind}")
    return voice_id


def _settings_for(language: str, kind: str = "artist") -> dict:
    profiles = TTS_PROFILES.get(language, TTS_PROFILES[DEFAULT_TTS_LANGUAGE])
    profile = profiles.get(kind, {})
    return profile.get("settings", {})


def _tts_key_for(artist: Artist) -> str:
    return f"artist/{artist.spotify_artist_id}.mp3"

def _prepare_text_for_tts(text: str, language: str) -> str:
    clean = (text or "").strip()

    if language == "es":
        return prepare_for_tts_es(
            clean,
            rank=None,
            track_name="",
            artist_name="",
            strip_markdown=True,
            number_normalize=True,
        )

    if language == "ptbr":
        return prepare_for_tts_pt_br(
            clean,
            rank=None,
            track_name="",
            artist_name="",
            strip_markdown=True,
            number_normalize=True,
        )

    return clean


def fetch_batch(
    session: Session,
    language: str | None,
    overwrite: bool,
    last_id: int,
) -> list[ArtistLocale]:
    stmt = (
        select(ArtistLocale, Artist)
        .join(Artist, Artist.id == ArtistLocale.artist_id)
        .where(ArtistLocale.id > last_id)
        .where(ArtistLocale.artist_description_text.is_not(None))  # type: ignore[attr-defined]
        .order_by(ArtistLocale.id)
        .limit(BATCH_SIZE)
    )

    if language:
        stmt = stmt.where(ArtistLocale.language_code == language)

    if not overwrite:
        stmt = stmt.where(ArtistLocale.tts_key.is_(None))  # type: ignore

    return list(session.exec(stmt).all())


def count_rows(session: Session, language: str | None = None) -> int:
    stmt = select(ArtistLocale).where(ArtistLocale.artist_description_text.is_not(None))  # type: ignore
    if language:
        stmt = stmt.where(ArtistLocale.language_code == language)
    return len(session.exec(stmt).all())


def count_done(session: Session, language: str | None = None) -> int:
    stmt = (
        select(ArtistLocale)
        .where(ArtistLocale.artist_description_text.is_not(None))  # type: ignore
        .where(ArtistLocale.tts_key.is_not(None))  # type: ignore
    )
    if language:
        stmt = stmt.where(ArtistLocale.language_code == language)
    return len(session.exec(stmt).all())


def main(language: str | None, overwrite: bool, limit: int | None) -> None:
    total_processed = 0
    batch_number = 1
    last_id = 0

    with Session(engine) as precheck_session:
        total_available = count_rows(precheck_session, language)
        total_done_before = count_done(precheck_session, language)
        logger.info(
            f"Starting artist locale TTS run | language={language or 'all'} | "
            f"total rows={total_available} | already done={total_done_before} | overwrite={overwrite}"
        )

    while True:
        with Session(engine) as session:
            rows = fetch_batch(session, language, overwrite, last_id)

            if not rows:
                logger.info("No more rows to process.")
                break

            if limit is not None:
                remaining = limit - total_processed
                if remaining <= 0:
                    break
                rows = rows[:remaining]

            logger.info(f"Starting batch {batch_number} with {len(rows)} row(s)...")

            processed_this_batch = 0

            for row, artist in rows:
                row_id = row.id
                artist_id = row.artist_id
                lang = _canon_lang(row.language_code)
                text = (row.artist_description_text or "").strip()

                last_id = row_id

                if not text:
                    logger.warning(f"Skipping row_id={row_id} artist_id={artist_id}: empty text")
                    continue

                try:
                    bucket = _bucket_for(lang)
                    if not artist.spotify_artist_id:
                        logger.warning(f"Skipping artist_id={artist.id}: missing spotify id")
                        continue

                    key = _tts_key_for(artist)
                    voice_id = _voice_for(lang, "artist")
                    settings = _settings_for(lang, "artist")

                    prepared_text = _prepare_text_for_tts(text, lang)
                    logger.info(f"PREPARED TEXT row_id={row_id} -> {repr(prepared_text)}")

                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        tmp_path = Path(tmp.name)

                    try:
                        generate_tts_mp3(
                            text=prepared_text,
                            out_path=tmp_path,
                            voice_id=voice_id,
                            overwrite=True,
                            play=False,
                            settings=settings,
                            language=lang,
                        )

                        upload_bytes(
                            bucket,
                            key,
                            tmp_path.read_bytes(),
                            content_type="audio/mpeg",
                        )

                        row.tts_bucket = bucket
                        row.tts_key = key
                        session.add(row)

                        processed_this_batch += 1
                        total_processed += 1

                        logger.info(
                            f"✅ row_id={row_id} artist_id={artist_id} lang={lang} "
                            f"-> {bucket}/{key}"
                        )

                    finally:
                        tmp_path.unlink(missing_ok=True)

                    time.sleep(PAUSE_BETWEEN_REQUESTS_SEC)

                except Exception as exc:
                    logger.exception(
                        f"❌ Failed row_id={row_id} artist_id={artist_id} lang={lang}: {exc}"
                    )
                    session.rollback()
                    break

            else:
                session.commit()

                done_now = count_done(session, language)
                logger.info(
                    f"Batch {batch_number} committed. "
                    f"Processed this batch: {processed_this_batch}. "
                    f"Total processed this run: {total_processed}. "
                    f"Total with MP3 now: {done_now}."
                )

                batch_number += 1
                if limit is not None and total_processed >= limit:
                    break

                time.sleep(PAUSE_BETWEEN_BATCHES_SEC)
                continue

            logger.warning("Stopping run after batch error. Restart the script to continue safely.")
            break

    with Session(engine) as final_session:
        final_done = count_done(final_session, language)
        logger.info(
            f"Done. Final MP3-linked rows for language={language or 'all'}: {final_done}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Optional: es, ptbr, or leave blank for all languages",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    lang = _canon_lang(args.language) if args.language else None
    main(language=lang, overwrite=args.overwrite, limit=args.limit)