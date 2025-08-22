from fastapi import APIRouter, Query, Depends
from pathlib import Path
import logging
from typing import Iterable, Optional, Set, Any, List, Dict

from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Track
from backend.config import VOICE_ID_TRACK
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger("tts_logger")

detail_router = APIRouter(
    prefix="/tts/detail",
    tags=["TTS - Track Detail"]
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def generate_detail_filename(item: Dict[str, str]) -> str:
    """
    Save files locally as <spotify_track_id>.mp3 to mirror storage keys.
    """
    return f"{item['spotify_track_id']}.mp3"


def _parse_count_to_limit(count_param: Optional[int]) -> Optional[int]:
    """
    Convert incoming count to a limit:
      - None or < 0  => unlimited (returns None)
      - 0            => 0 (nothing processed)
      - > 0          => that exact limit
    """
    try:
        raw = int(count_param) if count_param is not None else -1
    except (TypeError, ValueError):
        raw = -1
    return None if raw < 0 else raw


def _spotify_id_from(x: Any) -> Optional[str]:
    """
    Extract a spotify_track_id from diagnostics entries of varying shapes.
    Supports:
      - dict with "spotify_track_id" or "track_spotify_id"
      - object with .spotify_track_id
      - object with .track.spotify_track_id
      - plain string already equal to the ID
    """
    if isinstance(x, str):
        return x.strip() or None
    if isinstance(x, dict):
        return x.get("spotify_track_id") or x.get("track_spotify_id")
    sid = getattr(x, "spotify_track_id", None)
    if sid:
        return sid
    track_obj = getattr(x, "track", None)
    if track_obj:
        return getattr(track_obj, "spotify_track_id", None)
    return None


def _collect_missing_spotify_ids(missing_items: Iterable[Any]) -> List[str]:
    """
    Build an ordered, de-duplicated list of spotify_track_id strings.
    """
    seen: Set[str] = set()
    ordered: List[str] = []
    for it in missing_items:
        sid = _spotify_id_from(it)
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint (LOCAL DISK ONLY)
# ─────────────────────────────────────────────────────────────────────────────
@detail_router.post("/by-missing")
async def generate_missing_detail_tts(
    count: int = Query(-1, description="Number of missing detail TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Finds missing DETAIL MP3s by spotify_track_id (from diagnostics),
    loads matching Track rows directly, and generates MP3s to local disk.

    No Supabase upload occurs here.
    """
    limit = _parse_count_to_limit(count)
    logger.info("🧠 Generating up to %s missing detail TTS files (negative → unlimited)", count)

    # 1) Diagnose which Spotify IDs are missing
    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=False,
        check_detail_mp3=True,
        check_artist_mp3=False,
    )
    missing_diag = diagnostics.get("missing_mp3", {}).get("track_detail", []) or []
    missing_sids_all = _collect_missing_spotify_ids(missing_diag)

    logger.info("🧮 Missing detail MP3s detected (pre-limit): %d", len(missing_sids_all))
    if not missing_sids_all:
        logger.info("✅ Nothing to generate; all detail MP3s present.")
        return {"generated": 0, "skipped": 0, "missing_found": 0, "files": []}

    # Apply limit to the SID list
    missing_sids = missing_sids_all[:limit] if limit is not None else missing_sids_all

    # 2) Fetch Tracks directly by spotify_track_id
    q = (
        select(Track)
        .where(Track.spotify_track_id.in_(missing_sids))
        .options(selectinload(Track.artist))
    )
    tracks = db.exec(q).all()
    by_sid = {t.spotify_track_id: t for t in tracks}
    not_found = [sid for sid in missing_sids if sid not in by_sid]
    if not_found:
        logger.warning("⚠️ %d Spotify IDs not found in Track table (first few): %s",
                       len(not_found), not_found[:5])

    # 3) Build synthesis items, skipping rows without detail text
    items: List[Dict[str, str]] = []
    missing_text_count = 0

    for sid in missing_sids:
        t = by_sid.get(sid)
        if not t:
            continue
        if not t.detail or not t.detail.strip():
            missing_text_count += 1
            continue

        items.append({
            "track_id": t.id,
            "spotify_track_id": sid,
            "track_name": t.track_name,
            "artist_name": (t.artist.artist_name if t.artist else "Unknown Artist"),
            "album_name": t.album_name or "TopSpot40 Detail Tracks",
            "detail": t.detail,
            "language": "en",  # optional; used by your normalizer
        })

    logger.info("🎯 Ready to generate %d (of %d diagnosed) detail TTS files",
                len(items), len(missing_sids))
    logger.info("🚫 Skipped %d tracks due to missing detail text", missing_text_count)

    if not items:
        return {
            "generated": 0,
            "skipped": missing_text_count,
            "missing_found": len(missing_sids_all),
            "files": [],
            "message": "No eligible tracks with detail text to synthesize (or Tracks not found by spotify_track_id).",
        }

    # 4) LOCAL-ONLY: write MP3s to disk (no upload)
    return generate_tts_batch(
        items=items,
        text_key="detail",
        voice_id=VOICE_ID_TRACK,
        output_dir=Path("data/mp3_files/track_detail_mp3_files"),
        filename_func=generate_detail_filename,
        log_prefix="Track Detail",
        overwrite=overwrite,
        play=play,
        default_language="en",
        normalize=True,
    )
