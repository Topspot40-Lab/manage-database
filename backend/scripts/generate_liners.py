from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

import requests
from dotenv import load_dotenv


def safe_filename(name: str) -> str:
    """Convert text into a safe filename fragment."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def generate_tts_mp3(
    api_key: str,
    voice_id: str,
    text: str,
    output_path: Path,
    model_id: str = "eleven_multilingual_v2",
) -> None:
    """
    Generate one MP3 file using the ElevenLabs text-to-speech API.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75,
            "style": 0.20,
            "use_speaker_boost": True,
        },
    }

    response = requests.post(url, json=payload, headers=headers, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(
            f"ElevenLabs API error {response.status_code}: {response.text}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)


def build_liner_lines() -> list[str]:
    return [
        "You're listening to TopSpot40 — where every track tells a story.",
        "Hope you're enjoying the music journey with us.",
        "Sit back and let the memories play on TopSpot40.",
        "Great music never goes out of style — and neither do you.",
        "Thanks for tuning in to TopSpot40 — your soundtrack through time.",
        "Keep it right here — more classics coming your way.",
        "You're in the groove now — stay with us.",
        "The hits just keep on coming here at TopSpot40.",
        "Music that moves you — only on TopSpot40.",
        "Let the rhythm carry you a little further.",
        "From one great track to the next — TopSpot40.",
        "Taking you back, one song at a time.",
        "The soundtrack of your life continues right here.",
        "Stay tuned — more favorites just ahead.",
        "Bringing back the magic of music.",
        "You're right where the music lives.",
        "Timeless tunes, endless memories.",
        "Keep the dial locked on TopSpot40.",
        "Feel the vibe, feel the music.",
        "A little nostalgia goes a long way.",
        "You're cruising through the classics with TopSpot40.",
        "Every song has a memory — what's yours?",
        "Let the good times roll.",
        "Music that stands the test of time.",
        "More hits, more memories, more TopSpot40.",
        "The journey continues — stay with us.",
        "Just getting warmed up — plenty more ahead.",
        "Your personal time machine — TopSpot40.",
        "Where the past sounds better than ever.",
        "Thanks for listening — we've got more on the way.",
    ]


def main() -> None:
    load_dotenv()

    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("VOICE_ID_ARTIST")

    if not api_key:
        raise RuntimeError("Missing ELEVENLABS_API_KEY in .env")

    if not voice_id:
        raise RuntimeError("Missing ELEVENLABS_VOICE_ID in .env")

    output_dir = Path("liner_mp3_files")
    lines = build_liner_lines()

    print(f"Generating {len(lines)} liner files into: {output_dir.resolve()}")

    for index, line in enumerate(lines, start=1):
        filename = f"liner_{index:02}.mp3"
        output_path = output_dir / filename

        if output_path.exists():
            print(f"Skipping existing file: {filename}")
            continue

        print(f"[{index:02}/{len(lines):02}] Creating {filename}")
        generate_tts_mp3(
            api_key=api_key,
            voice_id=voice_id,
            text=line,
            output_path=output_path,
            model_id="eleven_multilingual_v2",
        )

    print("Done. All liner MP3 files created.")


if __name__ == "__main__":
    main()