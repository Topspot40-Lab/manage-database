from fastapi import APIRouter, Query, Depends
from pathlib import Path
import logging
from typing import Iterable, Optional, Set, Any, List, Dict

from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Track, TrackRanking, DecadeGenre
from backend.config import VOICE_ID_INTRO
from backend.utils.tts_diagnostics import get_missing_tts_info, normalize_for_filename
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger("tts_logger")

intro_router = APIRouter(
    prefix="/tts/intro",
    tags=["TTS - Intro"]
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def generate_intro_filename(item: Dict[str, Any]) -> str:
    """
    Local filename: <decade>_<genre>_<rank:02>.mp3  (no 'intro/' prefix)
    """
    decade = normalize_for_filename(item["decade"])
    genre  = normalize_for_filename(item["genre"])
    return f"{decade}_{genre}_{int(item['rank']):02}.mp3"

def _parse_count_to_limit(count_param: Optional[int]) -> Optional[int]:
    """
    None or <0 => unlimited (None); 0 => 0; >0 => that number
    """
    try:
        raw = int(count_param) if count_param is not None else -1
    except (TypeError, ValueError):
        raw = -1
    return None if raw < 0 else raw

def _basename_list(missing_items: Iterable[str]) -> List[str]:
    """
    From diagnostics like 'intro/1960s_latin_global_36.mp3',
    return ordered, de-duplicated basenames like '1960s_latin_global_36.mp3'.
    """
    seen: Set[str] = set()
    ordered: List[str] = []
    for s in missing_items:
        if not s:
            continue
        name = s.strip()
        # strip a leading 'intro/' if present
        if "/" in name:
            name = name.rsplit("/", 1)[-1]
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint (LOCAL DISK ONLY)
# ─────────────────────────────────────────────────────────────────────────────
@intro_router.post("/by-missing")
async def generate_missing_intro_tts(
    count: int = Query(-1, description="Number of missing intro TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Find missing INTRO MP3s using diagnostics, then generate the missing files
    to LOCAL DISK ONLY (no upload).
    """
    limit = _parse_count_to_limit(count)
    logger.info("🧠 Generating up to %s missing intro TTS files (negative → unlimited)", count)

    # 1) Diagnostics: which intro files are missing?
    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=True,
        check_detail_mp3=False,
        check_artist_mp3=False,
    )

    # Diagnostics returns keys like 'intro/<decade_genre_rank>.mp3'
    missing_keys = diagnostics.get("missing_mp3", {}).get("track_intro", []) or []
    missing_basenames_all = _basename_list(missing_keys)

    logger.info("🧮 Missing intro MP3s detected (pre-limit): %d", len(missing_basenames_all))
    if not missing_basenames_all:
        logger.info("✅ Nothing to generate; all intro MP3s present.")
        return {"generated": 0, "skipped": 0, "missing_found": 0, "files": []}

    # Apply count limit while preserving order
    chosen_basenames: List[str] = (
        missing_basenames_all if limit is None else missing_basenames_all[:limit]
    )
    chosen_set: Set[str] = set(chosen_basenames)

    # 2) Load rankings + related track/artist/decade/genre (used to reconstruct filename & text)
    rankings = db.exec(
        select(TrackRanking)
        .options(
            selectinload(TrackRanking.track),
            selectinload(TrackRanking.track).selectinload(Track.artist),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.decade),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.genre),
        )
    ).all()

    # 3) Build items for TTS where the computed basename matches a missing one
    items: List[Dict[str, Any]] = []
    missing_text_count = 0

    for ranking in rankings:
        track = ranking.track
        artist = track.artist
        decade = ranking.decade_genre.decade.decade_name
        genre = ranking.decade_genre.genre.genre_name

        # compute the basename to compare with diagnostics' basenames
        basename = generate_intro_filename({
            "decade": decade,
            "genre": genre,
            "rank": ranking.ranking,
        })  # already ends with .mp3

        if basename not in chosen_set:
            continue

        intro_text = ranking.intro or ""
        if not intro_text.strip():
            # (Your diagnostics said all intro texts are present, but keep guard.)
            missing_text_count += 1
            continue

        items.append({
            "track_id": track.id,
            "track_name": track.track_name,
            "artist_name": artist.artist_name if artist else "Unknown Artist",
            "album_name": track.album_name or "TopSpot40 Intro Tracks",
            "intro": intro_text,
            "rank": ranking.ranking,
            "decade": decade,
            "genre": genre,
            "language": "en",  # optional, used by normalizer if enabled
        })

        # Early stop if a positive count was requested and we've hit it
        if limit is not None and len(items) >= limit:
            break

    logger.debug("🧪 Found %d missing intro TTS items to generate", len(items))
    logger.info("🚫 Skipped %d tracks due to missing intro text", missing_text_count)

    if not items:
        return {
            "generated": 0,
            "skipped": missing_text_count,
            "missing_found": len(missing_basenames_all),
            "files": [],
            "message": "No eligible tracks to synthesize (basename mismatch or missing intro text).",
        }

    # 4) LOCAL-ONLY generation
    return generate_tts_batch(
        items=items,
        text_key="intro",
        voice_id=VOICE_ID_INTRO,
        output_dir=Path("data/mp3_files/track_intro_mp3_files"),
        filename_func=generate_intro_filename,  # produces '<decade>_<genre>_<rank>.mp3'
        log_prefix="Track Intro",
        overwrite=overwrite,
        play=play,
        default_language="en",
        normalize=True,
    )
