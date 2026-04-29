import argparse
import logging
import os
import time

from openai import OpenAI
from sqlalchemy import select as sa_select
from sqlmodel import Session, select

from backend.database import engine
from backend.models.dbmodels import Artist, ArtistLocale


client = OpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
)

BATCH_SIZE = 50
PAUSE_BETWEEN_REQUESTS_SEC = 0.3
PAUSE_BETWEEN_BATCHES_SEC = 2.0

logger = logging.getLogger("artist_locale_generator")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def generate_text(prompt: str) -> str:
    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a smooth, warm radio narrator writing artist descriptions. "
                    "Keep the tone relaxed, natural, and engaging. "
                    "Avoid exaggerated enthusiasm or hype phrases like greetings or exclamations. "
                    "Write in a calm, confident voice suitable for continuous listening. "
                    "Use clear, well-paced sentences that sound natural when spoken aloud. "
                    "Do not mention specific songs."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.6,
    )

    return response.choices[0].message.content.strip()


def build_prompt(language: str, artist_name: str, genres: str = "") -> str:
    genre_line = f"Genres: {genres}" if genres else "Genres: Unknown"

    if language == "es":
        return f"""
Escribe una descripción natural y atractiva del artista en español para una audiencia general amante de la música.

Requisitos:
- Exactamente de 2 a 3 oraciones completas
- Mantén las oraciones relativamente cortas y claras
- Enfócate en el estilo musical del artista, su personalidad, sus influencias y su impacto general
- Puedes mencionar sus raíces musicales o su contexto cultural si encaja de forma natural
- No describas canciones específicas ni menciones títulos de canciones
- Evita listas de fechas, premios o datos demasiado enciclopédicos
- Evita saludos, exclamaciones o frases de locutor exagerado
- Debe sonar natural para narración hablada, con tono cálido, fluido y agradable de escuchar
- Evita frases genéricas, repetitivas o demasiado largas

Artist: {artist_name}
{genre_line}
""".strip()

    if language == "pt-BR":
        return f"""
Escreva uma descrição natural e envolvente do artista em português do Brasil para um público geral que gosta de música.

Requisitos:
- Exatamente de 2 a 3 frases completas
- Mantenha as frases relativamente curtas e claras
- Foque no estilo musical do artista, sua personalidade, suas influências e seu impacto geral
- Você pode mencionar suas raízes musicais ou contexto cultural se encaixar de forma natural
- Não descreva músicas específicas nem liste títulos de faixas
- Evite listas de datas, prêmios ou fatos enciclopédicos demais
- Evite saudações, exclamações ou frases de locutor exagerado
- O texto deve soar natural para narração falada, com tom suave, fluido e agradável
- Evite frases genéricas, repetitivas ou muito longas

Artist: {artist_name}
{genre_line}
""".strip()

    raise ValueError(f"Unsupported language: {language}")


def upsert_artist_locale(
    session: Session,
    artist_id: int,
    language_code: str,
    artist_description: str,
    overwrite: bool = False,
) -> None:
    existing = session.exec(
        select(ArtistLocale)
        .where(ArtistLocale.artist_id == artist_id)
        .where(ArtistLocale.language_code == language_code)
    ).first()

    if existing:
        if overwrite:
            existing.artist_description_text = artist_description
            session.add(existing)
        return

    row = ArtistLocale(
        artist_id=artist_id,
        language_code=language_code,
        artist_description_text=artist_description,
    )
    session.add(row)


def count_artist_locale_rows(session: Session, language_code: str) -> int:
    return len(
        session.exec(
            select(ArtistLocale).where(ArtistLocale.language_code == language_code)
        ).all()
    )


def fetch_next_batch(session: Session, overwrite: bool) -> list[Artist]:
    if overwrite:
        stmt = select(Artist).order_by(Artist.id).limit(BATCH_SIZE)
        return list(session.exec(stmt).all())

    ptbr_subq = sa_select(ArtistLocale.artist_id).where(
        ArtistLocale.language_code == "pt-BR",
        ArtistLocale.artist_description_text.isnot(None)
    )

    stmt = (
        select(Artist)
        .where(Artist.id.not_in(ptbr_subq))
        .order_by(Artist.id)
        .limit(BATCH_SIZE)
    )
    return list(session.exec(stmt).all())


def main(limit: int | None, overwrite: bool) -> None:
    total_processed = 0
    batch_number = 1
    last_artist_id = 0

    with Session(engine) as session:
        while True:
            if overwrite:
                stmt = (
                    select(Artist)
                    .where(Artist.id > last_artist_id)
                    .order_by(Artist.id)
                    .limit(BATCH_SIZE)
                )
                artists = list(session.exec(stmt).all())
            else:
                artists = fetch_next_batch(session, overwrite=False)

            if not artists:
                logger.info("No more artists to process.")
                break

            if limit is not None:
                remaining = limit - total_processed
                if remaining <= 0:
                    break
                artists = artists[:remaining]

            logger.info(
                f"Starting batch {batch_number} with {len(artists)} artist(s)..."
            )

            batch_processed = 0

            for artist in artists:
                artist_name = getattr(artist, "artist_name", "Unknown Artist")
                genres = ""

                logger.info(f"Processing artist: {artist_name}")

                for language_code in ["pt-BR"]:
                    try:
                        prompt = build_prompt(language_code, artist_name, genres)
                        artist_description = generate_text(prompt)

                        upsert_artist_locale(
                            session=session,
                            artist_id=artist.id,
                            language_code=language_code,
                            artist_description=artist_description,
                            overwrite=overwrite,
                        )

                        time.sleep(PAUSE_BETWEEN_REQUESTS_SEC)

                    except Exception as exc:
                        logger.exception(
                            f"Failed for artist_id={artist.id}, "
                            f"artist_name={artist_name}, language={language_code}: {exc}",
                            session.rollback()
                        )
                        continue

                batch_processed += 1
                total_processed += 1
                last_artist_id = artist.id

            session.commit()

            current_es = count_artist_locale_rows(session, "es")
            current_ptbr = count_artist_locale_rows(session, "pt-BR")

            logger.info(
                f"Batch {batch_number} committed. "
                f"Artists processed this batch: {batch_processed}. "
                f"Total processed: {total_processed}. "
                f"ES rows: {current_es}. PTBR rows: {current_ptbr}."
            )

            batch_number += 1

            if limit is not None and total_processed >= limit:
                break

            time.sleep(PAUSE_BETWEEN_BATCHES_SEC)

        logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    main(limit=args.limit, overwrite=args.overwrite)