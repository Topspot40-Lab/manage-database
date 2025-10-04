#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import os
from typing import Iterable, Tuple

from sqlalchemy import create_engine, text
from gtts import gTTS


# Base output folder (change if you like)
OUT_BASE = Path("data") / "mp3_files" / "seed_intro_mp3"

def rows(conn, sql: str) -> Iterable[Tuple[str, str]]:
    # Expect (slug, description)
    for slug, desc in conn.execute(text(sql)).fetchall():
        if slug and desc and str(desc).strip():
            yield slug, str(desc)

def safe(s: str) -> str:
    # Keep filenames friendly on all OSes
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s)

def dump_set(conn, sql: str, subfolder: str, lang: str = "en", refresh: bool = False):
    dest = OUT_BASE / subfolder
    dest.mkdir(parents=True, exist_ok=True)

    made = skipped = 0
    for slug, desc in rows(conn, sql):
        out = dest / f"{safe(slug)}.mp3"  # EXACTLY {slug}.mp3
        if out.exists() and not refresh:
            skipped += 1
            continue
        tts = gTTS(desc, lang=lang)
        tts.save(str(out))
        made += 1
        print("Wrote", out)
    print(f"[{subfolder}] made={made} skipped={skipped}")

def main():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL (e.g. postgresql+psycopg2://postgres:pass@localhost:5432/postgres)")

    # optional envs:
    lang = os.getenv("TTS_LANG", "en")        # e.g. "en" or "es"
    refresh = os.getenv("TTS_REFRESH", "0") in ("1","true","yes")

    eng = create_engine(dsn, future=True)
    with eng.begin() as conn:
        # Decades (needs decade.slug + decade.description)
        dump_set(conn,
                 "select slug, description from public.decade where description is not null and description <> ''",
                 "decades", lang=lang, refresh=refresh)

        # Genres (needs genre.slug + genre.description)
        dump_set(conn,
                 "select slug, description from public.genre where description is not null and description <> ''",
                 "genres", lang=lang, refresh=refresh)

        # Combos (needs decade_genre.slug + decade_genre.description)
        dump_set(conn,
                 "select slug, description from public.decade_genre where description is not null and description <> ''",
                 "combos", lang=lang, refresh=refresh)

if __name__ == "__main__":
    main()
