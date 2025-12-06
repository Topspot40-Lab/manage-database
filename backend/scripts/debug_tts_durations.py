# backend/scripts/debug_tts_durations.py
from __future__ import annotations

import asyncio
from typing import Literal

from backend.services.audio_duration import get_mp3_duration_ms

# Adjust these as needed
LANG: Literal["en", "es", "pt-BR"] = "en"
DECADE = "1960s"
GENRE = "country"

# ranks to check
START_RANK = 1
END_RANK = 40

# KINDS: list[str] = ["intro", "detail", "artist"]
KINDS: list[str] = ["intro"]


def build_filename(decade: str, genre: str, rank: int) -> str:
    """
    Matches your ElevenLabs naming scheme, e.g.
    1960s_country_01.mp3
    """
    return f"{decade}_{genre}_{rank:02d}.mp3"


def bucket_for_lang(lang: str) -> str:
    """
    Simple mapping based on your Supabase buckets.
    """
    if lang == "en":
        return "audio-en"
    if lang == "es":
        return "audio-es"
    if lang == "pt-BR":
        return "audio-ptbr"
    raise ValueError(f"Unsupported lang: {lang}")


async def main() -> None:
    bucket = bucket_for_lang(LANG)
    print(f"🔎 Checking durations in bucket={bucket}, decade={DECADE}, genre={GENRE}")
    print()

    for rank in range(START_RANK, END_RANK + 1):
        fname = build_filename(DECADE, GENRE, rank)
        row: dict[str, int | None] = {}
        some_ok = False

        for kind in KINDS:
            key = f"{kind}/{fname}"  # e.g. intro/1960s_country_01.mp3
            ms = await get_mp3_duration_ms(bucket, key)
            row[kind] = ms
            if ms is not None:
                some_ok = True

        if not some_ok:
            # No MP3 found for any kind at this rank — skip printing noise
            continue

        # Print a compact summary line
        intro_ms = row.get("intro")
        detail_ms = row.get("detail")
        artist_ms = row.get("artist")

        def fmt(ms: int | None) -> str:
            if ms is None:
                return "-"
            sec = ms / 1000
            return f"{ms:5d} ms ({sec:5.2f}s)"

        print(
            f"Rank {rank:02d}: "
            f"intro={fmt(intro_ms)} | "
            f"detail={fmt(detail_ms)} | "
            f"artist={fmt(artist_ms)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
