import os
import time
import json

from dotenv import load_dotenv
from openai import OpenAI
from sqlmodel import Session, select

from backend.database import engine
from backend.models.dbmodels import TrackLocale

load_dotenv()

client = OpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
)

BATCH_SIZE = 50
PAUSE_BETWEEN_REQUESTS_SEC = 0.0
PAUSE_BETWEEN_BATCHES_SEC = 2.0
TRANSLATION_GROUP_SIZE = 10

def translate_group_to_ptbr(rows: list[TrackLocale]) -> list[dict]:
    payload = [
        {
            "track_id": row.track_id,
            "detail_text": row.detail_text.strip(),
        }
        for row in rows
    ]

    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate the provided Spanish texts into natural Brazilian Portuguese. "
                    "Return ONLY valid JSON. Do not add markdown, comments, or explanation. "
                    "Output a JSON array of objects. "
                    "Each object must contain exactly these keys: "
                    '"track_id", "detail_text". '

                    "Rules: "
                    "Output only Brazilian Portuguese. "
                    "Do not include Spanish words or Spanish verb forms. "
                    "Do not translate song titles. "
                    "Avoid 'sanação'; use 'cura' or 'recuperação'. "
                    "Keep tone natural and conversational. "
                    "Preserve meaning. "
                    "Do not summarize."
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
    return json.loads(content)

def translate_to_ptbr(spanish_text: str) -> str:
    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate the user's Spanish text into natural Brazilian Portuguese. "
                    "Output only Brazilian Portuguese. Do not include any Spanish words or Spanish verb forms. "
                    "If a word exists in both languages, ensure it is used in correct Brazilian Portuguese form. "
                    "Do not translate song titles. Keep titles exactly as they appear in the source text. "
                    "If a term is not natural in Brazilian Portuguese, replace it with a natural equivalent. "
                    "Avoid unnatural words such as 'sanação'; prefer natural terms like 'cura' or 'recuperação'. "
                    "Keep the tone warm, smooth, and conversational, like a polished radio narrator. "
                    "Preserve the original meaning and sentence structure closely. "
                    "Do not summarize. Do not shorten. Do not add filler expressions or extra commentary. "
                    "Avoid adding phrases like 'ah', 'olha só', 'sabe'. "
                    "Use vocabulary that sounds natural to a native Brazilian Portuguese speaker."
                ),
            },
            {
                "role": "user",
                "content": spanish_text,
            },
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content.strip()


from sqlalchemy import select as sa_select

def fetch_next_batch(session: Session) -> list[TrackLocale]:
    stmt = (
        select(TrackLocale)
        .where(TrackLocale.language_code == "es")
        .where(
            ~TrackLocale.track_id.in_(
                sa_select(TrackLocale.track_id).where(TrackLocale.language_code == "ptbr")
            )
        )
        .order_by(TrackLocale.track_id)
        .limit(BATCH_SIZE)
    )

    return list(session.exec(stmt).all())

def count_ptbr_rows(session: Session) -> int:
    rows = session.exec(
        select(TrackLocale).where(TrackLocale.language_code == "ptbr")
    ).all()
    return len(rows)


def count_es_rows(session: Session) -> int:
    rows = session.exec(
        select(TrackLocale).where(TrackLocale.language_code == "es")
    ).all()
    return len(rows)


def process_batch(session: Session, batch_number: int) -> int:
    rows = fetch_next_batch(session)

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
                item["track_id"]: item["detail_text"].strip()
                for item in translated_items
            }

            for row in group:
                translated_text = translated_by_id.get(row.track_id)

                if not translated_text:
                    print(f"Missing translation for track_id={row.track_id}")
                    continue

                new_row = TrackLocale(
                    track_id=row.track_id,
                    language_code="ptbr",
                    detail_text=translated_text,
                    tts_bucket="audio-ptbr",
                    tts_key=None,
                )

                session.add(new_row)
                inserted_count += 1

            print(f"Batch {batch_number}: {inserted_count}/{len(rows)} rows done...")

        except Exception as e:
            print(f"Error in group starting at track_id={group[0].track_id}: {e}")
            print("Skipping this group and continuing...")
            print("-" * 80)

            continue  # <-- important

    session.commit()
    print(f"Batch {batch_number} committed: {inserted_count} rows inserted.")
    return inserted_count


def main() -> None:
    with Session(engine) as session:
        total_es = count_es_rows(session)
        print(f"Total Spanish rows available: {total_es}")

        batch_number = 1
        total_inserted_this_run = 0

        while True:
            inserted = process_batch(session, batch_number)

            if inserted == 0:
                break

            total_inserted_this_run += inserted
            current_ptbr = count_ptbr_rows(session)

            print(f"PTBR rows currently in database: {current_ptbr}")
            print(f"Inserted in this run so far: {total_inserted_this_run}")

            batch_number += 1

            if PAUSE_BETWEEN_BATCHES_SEC > 0:
                time.sleep(PAUSE_BETWEEN_BATCHES_SEC)

        final_ptbr = count_ptbr_rows(session)
        print("\nDone.")
        print(f"Final PTBR count: {final_ptbr}")
        print(f"Total inserted in this run: {total_inserted_this_run}")


if __name__ == "__main__":
    main()