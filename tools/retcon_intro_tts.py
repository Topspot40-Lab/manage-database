# backend/tools/retcon_intro_tts.py
from __future__ import annotations

import argparse
import logging
import re
import shutil
from pathlib import Path
from typing import Iterable

from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

# --- Project imports (use your existing modules) ---
from backend.database import get_db
from backend.models import TrackRanking, DecadeGenre, Track, Artist
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.tts.generate_tts_batch import generate_tts_batch
from backend.config import VOICE_ID_INTRO

log = logging.getLogger("retcon_intro_tts")

# Patterns to detect “problem” intros that likely say “hashtag”
RE_HASH_NUM = re.compile(r"\B#\d+\b", re.IGNORECASE)
# Optional: also catch "No. 14", "N.º 14", etc. If you want to include these, set --include-no
RE_NO_NUM_ANY = re.compile(r"\bN(?:o\.?|[º°o]\.?)\s*\d+\b", re.IGNORECASE)

DEFAULT_OUTPUT_DIR = Path("data/mp3_files/track_intro_mp3_files")


def generate_intro_filename(decade: str, genre: str, rank: int) -> str:
    d = normalize_for_filename(decade)
    g = normalize_for_filename(genre)
    return f"{d}_{g}_{rank:02}.mp3"


def find_candidates(db: Session, include_no: bool) -> Iterable[dict]:
    """
    Yield items for intros that match #NN (and optionally No. NN).
    """
    results = db.exec(
        select(TrackRanking)
        .options(
            selectinload(TrackRanking.track),
            selectinload(TrackRanking.track).selectinload(Track.artist),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.decade),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.genre),
        )
    ).all()

    for ranking in results:
        intro = (ranking.intro or "").strip()
        if not intro:
            continue

        hit = bool(RE_HASH_NUM.search(intro))
        if include_no:
            hit = hit or bool(RE_NO_NUM_ANY.search(intro))
        if not hit:
            continue

        track = ranking.track
        artist = track.artist
        decade = ranking.decade_genre.decade.decade_name
        genre = ranking.decade_genre.genre.genre_name
        filename = generate_intro_filename(decade, genre, ranking.ranking)

        yield {
            "track_id": track.id,
            "track_name": track.track_name,
            "artist_name": artist.artist_name,
            "album_name": track.album_name or "TopSpot40 Intro Tracks",
            "intro": intro,
            "rank": ranking.ranking,
            "decade": decade,
            "genre": genre,
            # optional language field if you later mix EN/ES:
            "language": "en",
            "filename": filename,
        }


def backup_file(path: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / path.name
    try:
        shutil.copy2(path, dest)
        log.info("🗂️  Backed up %s -> %s", path, dest)
    except Exception as e:
        log.warning("Backup failed for %s: %s", path, e)


def main():
    parser = argparse.ArgumentParser(
        description="Re-generate intro MP3s whose text contains #NN (and optionally 'No. NN')."
    )
    parser.add_argument("--limit", type=int, default=-1, help="Max files to (re)generate. -1 = all.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory of intro MP3 files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--include-no",
        action="store_true",
        help="Also fix 'No. 14' / 'N.º 14' variants (convert to 'number 14' at TTS time).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done; do not write files.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing MP3s (default: off).")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="If set, copy existing MP3s here before overwriting.",
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="If your pipeline supports it, play each MP3 after generating.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logger level for this tool.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))
    log.info("🔧 Starting retcon — output_dir=%s, include_no=%s, dry_run=%s, overwrite=%s",
             args.output_dir, args.include_no, args.dry_run, args.overwrite)

    # DB session from your app
    with get_db() as db:
        candidates = list(find_candidates(db, include_no=args.include_no))

    if args.limit > 0:
        candidates = candidates[: args.limit]

    if not candidates:
        log.info("✅ No matching intros found. Nothing to do.")
        return

    log.info("Found %d intros to (re)generate.", len(candidates))

    # Make sure filenames end with .mp3 and locate full paths for backup/overwrite decisions
    def filename_func(item: dict) -> str:
        fname = item["filename"]
        return fname if fname.lower().endswith(".mp3") else f"{fname}.mp3"

    # Dry-run: list what we'd do and exit
    if args.dry_run:
        for it in candidates:
            out = args.output_dir / filename_func(it)
            exists = out.exists()
            log.info("DRY-RUN would %s %s (exists=%s) — %s / %s #%02d",
                     "overwrite" if (exists and args.overwrite) else "write",
                     out, exists, it["decade"], it["genre"], it["rank"])
        log.info("DRY-RUN complete.")
        return

    # Backup existing files if requested
    if args.backup_dir:
        for it in candidates:
            out = args.output_dir / filename_func(it)
            if out.exists():
                backup_file(out, args.backup_dir)

    # Actually (re)generate via your existing batch pipeline.
    # NOTE: generate_tts_batch will normalize text right before TTS
    # if you applied the earlier patch (normalize=True by default).
    result = generate_tts_batch(
        items=candidates,
        text_key="intro",
        voice_id=VOICE_ID_INTRO,
        output_dir=args.output_dir,
        filename_func=lambda it: filename_func(it),
        log_prefix="Track Intro (retcon)",
        overwrite=args.overwrite,
        play=args.play,
        default_language="en",
        normalize=True,
    )

    log.info(result["message"])
    for p in result["files"]:
        log.debug("Wrote: %s", p)


if __name__ == "__main__":
    main()
