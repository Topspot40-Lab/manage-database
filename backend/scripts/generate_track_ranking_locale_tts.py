import argparse
import logging
import re
import tempfile
import time
from pathlib import Path

from sqlmodel import Session, select

from backend.database import engine
from backend.models.dbmodels import (
    TrackRankingLocale,
    TrackRanking,
    DecadeGenre,
    Decade,
    Genre,
)
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.services.supabase_storage import upload_bytes
from backend.config.tts import TTS_PROFILES, DEFAULT_TTS_LANGUAGE
from backend.services.tts_prep import prepare_for_tts_pt_br


logger = logging.getLogger("track_ranking_locale_tts")
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

def _tts_profile_lang(language: str) -> str:
    cleaned = (language or "").strip().lower()
    if cleaned in {"ptbr", "pt-br", "pt_br"}:
        return "pt-BR"
    if cleaned == "es":
        return "es"
    return "en"


def _voice_for(language: str, kind: str = "intro") -> str:
    profile_lang = _tts_profile_lang(language)
    profiles = TTS_PROFILES.get(profile_lang, TTS_PROFILES[DEFAULT_TTS_LANGUAGE])
    profile = profiles.get(kind, {})
    voice_id = profile.get("voice_id")
    if not voice_id:
        raise ValueError(f"No voice_id configured for language={profile_lang}, kind={kind}")
    return voice_id


def _settings_for(language: str, kind: str = "intro") -> dict:
    profile_lang = _tts_profile_lang(language)
    profiles = TTS_PROFILES.get(profile_lang, TTS_PROFILES[DEFAULT_TTS_LANGUAGE])
    profile = profiles.get(kind, {})
    return profile.get("settings", {})


def _slug(text: str) -> str:
    value = (text or "").strip().lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def _tts_key_for(decade, genre, ranking):
    decade_slug = decade.slug
    genre_slug = genre.slug
    return f"intro/{decade_slug}_{genre_slug}_{ranking:02d}.mp3"


def _prepare_text_for_tts(text: str, language: str) -> str:
    clean = (text or "").strip()

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
) -> list[tuple[TrackRankingLocale, TrackRanking, Decade, Genre]]:
    stmt = (
        select(TrackRankingLocale, TrackRanking, Decade, Genre)
        .join(TrackRanking, TrackRanking.id == TrackRankingLocale.track_ranking_id)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .join(Decade, Decade.id == DecadeGenre.decade_id)
        .join(Genre, Genre.id == DecadeGenre.genre_id)
        .where(TrackRankingLocale.id > last_id)
        .where(TrackRankingLocale.intro_text.is_not(None))  # type: ignore[attr-defined]
        .order_by(TrackRankingLocale.id)
        .limit(BATCH_SIZE)
    )

    if language:
        stmt = stmt.where(TrackRankingLocale.language_code == language)

    if not overwrite:
        stmt = stmt.where(TrackRankingLocale.tts_key.is_(None))  # type: ignore

    return list(session.exec(stmt).all())


def count_rows(session: Session, language: str | None = None) -> int:
    stmt = select(TrackRankingLocale).where(
        TrackRankingLocale.intro_text.is_not(None)  # type: ignore[attr-defined]
    )
    if language:
        stmt = stmt.where(TrackRankingLocale.language_code == language)
    return len(session.exec(stmt).all())


def count_done(session: Session, language: str | None = None) -> int:
    stmt = (
        select(TrackRankingLocale)
        .where(TrackRankingLocale.intro_text.is_not(None))  # type: ignore[attr-defined]
        .where(TrackRankingLocale.tts_key.is_not(None))  # type: ignore
    )
    if language:
        stmt = stmt.where(TrackRankingLocale.language_code == language)
    return len(session.exec(stmt).all())


def main(language: str | None, overwrite: bool, limit: int | None) -> None:
    total_processed = 0
    batch_number = 1
    last_id = 0

    with Session(engine) as precheck_session:
        total_available = count_rows(precheck_session, language)
        total_done_before = count_done(precheck_session, language)
        logger.info(
            f"Starting track ranking locale TTS run | language={language or 'all'} | "
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

            for row, ranking_row, decade, genre in rows:
                row_id = row.id
                ranking_id = row.track_ranking_id
                ranking = ranking_row.ranking
                lang = _canon_lang(row.language_code)
                text = (row.intro_text or "").strip()

                last_id = row_id

                if not text:
                    logger.warning(
                        f"Skipping row_id={row_id} track_ranking_id={ranking_id}: empty intro_text"
                    )
                    continue

                try:
                    if lang != "ptbr":
                        logger.warning(
                            f"Skipping row_id={row_id} track_ranking_id={ranking_id}: "
                            f"script is intended for ptbr, found language={lang}"
                        )
                        continue

                    bucket = _bucket_for(lang)
                    key = _tts_key_for(decade, genre, ranking)
                    voice_id = _voice_for(lang, "intro")
                    settings = _settings_for(lang, "intro")

                    prepared_text = _prepare_text_for_tts(text, lang)
                    logger.info(
                        f"PREPARED TEXT row_id={row_id} ranking_id={ranking_id} -> {repr(prepared_text)}"
                    )

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
                            f"✅ row_id={row_id} track_ranking_id={ranking_id} "
                            f"rank={ranking} lang={lang} -> {bucket}/{key}"
                        )

                    finally:
                        tmp_path.unlink(missing_ok=True)

                    time.sleep(PAUSE_BETWEEN_REQUESTS_SEC)

                except Exception as exc:
                    logger.exception(
                        f"❌ Failed row_id={row_id} track_ranking_id={ranking_id} lang={lang}: {exc}"
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
        default="ptbr",
        help="Optional: ptbr, es, en",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    lang = _canon_lang(args.language) if args.language else None
    main(language=lang, overwrite=args.overwrite, limit=args.limit)