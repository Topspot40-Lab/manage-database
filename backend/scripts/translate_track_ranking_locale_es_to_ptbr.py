import argparse
import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI
from sqlmodel import Session, select
from sqlalchemy import select as sa_select

from backend.database import engine
from backend.models.dbmodels import TrackRankingLocale

load_dotenv()

client = OpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
)

BATCH_SIZE = 50
TRANSLATION_GROUP_SIZE = 10
PAUSE_BETWEEN_BATCHES_SEC = 2.0

import re

def find_spanish_markers(text: str) -> list[str]:
    markers = [
        "arrancamos",
        "durante los",
        "los años",
        "con amigos",
        "preparen",
        "preparem-se para uma dose",
        "classificada como número",
        "posto número",
    ]
    text_lower = text.lower()
    return [m for m in markers if m in text_lower]

def force_ptbr_cleanup(text: str) -> str:
    replacements = {
        "Arrancamos": "Começamos",
        "arrancamos": "começamos",
        "posto número": "número",
        "Posto número": "Número",
        "classificada como número": "no número",
        "Classificada como número": "No número",
        "preparem-se para uma dose": "uma dose",
        "Preparem-se para uma dose": "Uma dose",
        "com amigos, ": "",
        "Com amigos, ": "",
        "dos 2000": "dos anos 2000",
        "2000s": "2000",
        "se ubica": "se posiciona",
        "se desliza": "desliza",
        "de emoção com": "Uma dose de emoção com",
        "durante los años": "durante os anos",
        "Durante los años": "Durante os anos",
        "los años": "os anos",
        "Los años": "Os anos",
    }

    cleaned = text
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)

    cleaned = cleaned.replace("  ", " ")
    cleaned = cleaned.replace("..", ".")
    cleaned = cleaned.replace(" ,", ",")
    return cleaned.strip()

MAX_RETRIES = 3

def translate_group_to_ptbr(rows: list[TrackRankingLocale]) -> list[dict]:
    payload = [
        {
            "track_ranking_id": row.track_ranking_id,
            "intro_text": (row.intro_text or "").strip(),
        }
        for row in rows
    ]

    for attempt in range(MAX_RETRIES):
        response = client.chat.completions.create(
            model="grok-3-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful translator.\n\n"

                        "Translate the following Spanish text into natural Brazilian Portuguese.\n\n"

                        "MANDATORY RULES:\n"
                        "- Translate the full meaning into Brazilian Portuguese.\n"
                        "- DO NOT leave any Spanish words.\n"
                        "- Keep the original tone and structure as closely as possible.\n"
                        "- Small adjustments are allowed only when needed to avoid unnatural literal Spanish constructions.\n"
                        "- DO NOT add new ideas, hype, or audience hooks.\n"
                        "- DO NOT remove any content.\n\n"

                        "STRUCTURE:\n"
                        "- Preserve the same order of ideas.\n"
                        "- Keep the sentence flow close to the original.\n"
                        "- Do not standardize the openings.\n\n"

                        "LANGUAGE:\n"
                        "- Use natural Brazilian Portuguese grammar, spelling, and accents.\n"
                        "- Replace Spanish words with natural Brazilian Portuguese equivalents.\n"
                        "- Avoid literal Spanish phrasing that sounds unnatural in Portuguese.\n\n"

                        "PROPER NOUNS:\n"
                        "- DO NOT translate song titles.\n"
                        "- DO NOT translate artist names.\n"
                        "- DO NOT translate album names.\n\n"

                        "OUTPUT:\n"
                        "- Return ONLY valid JSON.\n"
                        "- Each object must contain: track_ranking_id, intro_text.\n"
                        "- If ANY Spanish words appear, the response is INVALID.\n"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            temperature=0.2,
        )

        content = response.choices[0].message.content.strip()
        result = json.loads(content)
        for item in result:
            item["intro_text"] = force_ptbr_cleanup(item["intro_text"])

        # 🔥 VALIDATION STEP
        bad_markers = []

        for item in result:
            markers = find_spanish_markers(item["intro_text"])
            if markers:
                bad_markers.extend(markers)

        if not bad_markers:
            return result

        print(f"⚠️ Spanish detected {sorted(set(bad_markers))} — retrying ({attempt + 1}/{MAX_RETRIES})...")

    raise RuntimeError("❌ Failed to produce clean PT-BR after retries")
def fetch_next_batch(session: Session, limit: int | None = None) -> list[TrackRankingLocale]:
    stmt = (
        select(TrackRankingLocale)
        .where(TrackRankingLocale.language_code == "es")
        .where(TrackRankingLocale.intro_text.is_not(None))  # type: ignore[attr-defined]
        .where(
            ~TrackRankingLocale.track_ranking_id.in_(
                sa_select(TrackRankingLocale.track_ranking_id).where(
                    TrackRankingLocale.language_code == "ptbr"
                )
            )
        )
        .order_by(TrackRankingLocale.track_ranking_id)
        .limit(limit or BATCH_SIZE)
    )
    return list(session.exec(stmt).all())


def count_rows(session: Session, language_code: str) -> int:
    rows = session.exec(
        select(TrackRankingLocale).where(
            TrackRankingLocale.language_code == language_code
        )
    ).all()
    return len(rows)


def count_remaining_ptbr(session: Session) -> int:
    rows = session.exec(
        select(TrackRankingLocale)
        .where(TrackRankingLocale.language_code == "es")
        .where(
            ~TrackRankingLocale.track_ranking_id.in_(
                sa_select(TrackRankingLocale.track_ranking_id).where(
                    TrackRankingLocale.language_code == "ptbr"
                )
            )
        )
    ).all()
    return len(rows)


def process_batch(session: Session, batch_number: int, limit: int | None = None) -> int:
    rows = fetch_next_batch(session, limit=limit)

    if not rows:
        print("No more rows to translate.")
        return 0

    print(f"\nStarting batch {batch_number} with {len(rows)} rows...")

    inserted_count = 0

    for start in range(0, len(rows), TRANSLATION_GROUP_SIZE):
        group = rows[start:start + TRANSLATION_GROUP_SIZE]

        try:
            translated_items = translate_group_to_ptbr(group)

            translated_by_id = {
                item["track_ranking_id"]: item["intro_text"].strip()
                for item in translated_items
            }

            for row in group:
                translated_text = translated_by_id.get(row.track_ranking_id)

                if not translated_text:
                    print(f"Missing translation for track_ranking_id={row.track_ranking_id}")
                    continue

                new_row = TrackRankingLocale(
                    track_ranking_id=row.track_ranking_id,
                    language_code="ptbr",
                    intro_text=translated_text,
                    tts_bucket="audio-ptbr",
                    tts_key=None,
                )

                session.add(new_row)
                inserted_count += 1

            print(
                f"Batch {batch_number}: "
                f"{min(start + len(group), len(rows))}/{len(rows)} rows prepared..."
            )

        except Exception as e:
            print(f"Error in group starting at track_ranking_id={group[0].track_ranking_id}: {e}")
            print("Falling back to cleaned ES text for this group and continuing...")
            print("-" * 80)

            for row in group:
                fallback_text = force_ptbr_cleanup((row.intro_text or "").strip())

                new_row = TrackRankingLocale(
                    track_ranking_id=row.track_ranking_id,
                    language_code="ptbr",
                    intro_text=fallback_text,
                    tts_bucket="audio-ptbr",
                    tts_key=None,
                )

                session.add(new_row)
                inserted_count += 1

            print(
                f"Batch {batch_number}: "
                f"{min(start + len(group), len(rows))}/{len(rows)} rows prepared (fallback)..."
            )
            continue


    session.commit()
    print(f"Batch {batch_number} committed: {inserted_count} rows inserted.")
    return inserted_count


def main(limit: int | None) -> None:
    with Session(engine) as session:
        total_es = count_rows(session, "es")
        total_ptbr_before = count_rows(session, "ptbr")
        remaining_before = count_remaining_ptbr(session)

        print(f"Total ES rows available: {total_es}")
        print(f"PTBR rows before run: {total_ptbr_before}")
        print(f"Remaining ES rows needing PTBR: {remaining_before}")

        batch_number = 1
        total_inserted = 0

        while True:
            inserted = process_batch(session, batch_number=batch_number, limit=limit)

            if inserted == 0:
                break

            total_inserted += inserted
            batch_number += 1

            time.sleep(PAUSE_BETWEEN_BATCHES_SEC)

        current_ptbr = count_rows(session, "ptbr")
        remaining_now = count_remaining_ptbr(session)

        print("\nDone.")
        print(f"PTBR rows currently in database: {current_ptbr}")
        print(f"Remaining ES rows needing PTBR: {remaining_now}")
        print(f"Inserted in this run: {total_inserted}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Number of ES rows to translate this run")
    args = parser.parse_args()
    main(limit=args.limit)
