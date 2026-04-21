import os
import time
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("VOICE_ID_TRACK")  # <-- using your chosen voice
DATABASE_URL = os.getenv("POSTGRES_URL")

OUTPUT_DIR = Path(
    r"C:\Users\Owner\pp\topspot_json_creator\data\mp3_files\decade_genre_intro_mp3_files"
)

ELEVENLABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"


def validate_env():
    missing = []
    if not ELEVENLABS_API_KEY:
        missing.append("ELEVENLABS_API_KEY")
    if not ELEVENLABS_VOICE_ID:
        missing.append("VOICE_ID_TRACK")
    if not DATABASE_URL:
        missing.append("POSTGRES_URL")

    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")


def fetch_rows(test_mode=True):
    """
    test_mode=True  -> generates ONE file (safe test)
    test_mode=False -> generates ALL files
    """
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    try:
        with conn.cursor() as cur:
            if test_mode:
                cur.execute(
                    """
                    SELECT slug, description
                    FROM decade_genre
                    WHERE slug = '1980s-pop'
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT slug, description
                    FROM decade_genre
                    WHERE description IS NOT NULL
                      AND TRIM(description) <> ''
                    ORDER BY slug
                    """
                )

            rows = cur.fetchall()
            return [(slug, description) for slug, description in rows]
    finally:
        conn.close()


def generate_mp3(text: str, out_path: Path):
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75,
        },
    }

    response = requests.post(ELEVENLABS_URL, headers=headers, json=payload, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs error for {out_path.name}: "
            f"{response.status_code} {response.text}"
        )

    out_path.write_bytes(response.content)


def main():
    validate_env()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 🔹 CHANGE THIS AFTER TESTING
    TEST_MODE = False

    rows = fetch_rows(test_mode=TEST_MODE)
    print(f"Found {len(rows)} rows.")

    created = 0
    skipped = 0

    for slug, description in rows:
        filename = f"{slug}.mp3"
        out_path = OUTPUT_DIR / filename

        if out_path.exists():
            print(f"Skipping existing file: {filename}")
            skipped += 1
            continue

        print(f"Generating: {filename}")
        generate_mp3(description, out_path)
        created += 1

        # small delay to be nice to API
        time.sleep(0.5)

    print()
    print(f"Done. Created: {created}, Skipped: {skipped}")
    print(f"Files saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()