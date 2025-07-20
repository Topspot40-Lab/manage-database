from pathlib import Path
import random
from typing import Optional, Dict, Any

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 Track Cache — Loaded from JSON
# ─────────────────────────────────────────────────────────────────────────────
track_cache: Dict[str, Any] = {
    "filename": None,
    "tracks": [],
    "rankings": [],  # ✅ New: cache for ranking table
    "last_played_rank": None
}

from backend.utils.json_helpers import load_full_json_file
from backend.utils.logger_factory import get_step_logger

logger_step1c = get_step_logger("STEP_1.C")

def load_tracks_from_file(filename: str, full_path: Path) -> bool:
    try:
        logger_step1c.info(f"📂 Loading track file: {full_path}")
        data = load_full_json_file(file_path=full_path)

        if not isinstance(data, dict):
            logger_step1c.error(f"❌ Unexpected data format. Expected dict, got {type(data)}")
            return False

        track_tables = data.get("track_tables", {})
        tracks = track_tables.get("track", [])

        ranking_tables = data.get("ranking_tables", {})
        rankings = ranking_tables.get("track_ranking", [])

        if not isinstance(tracks, list):
            logger_step1c.error("❌ 'track' is not a list.")
            return False
        if not isinstance(rankings, list):
            logger_step1c.warning("⚠️ 'track_ranking' is missing or not a list. Defaulting to empty.")

        track_cache["filename"] = filename
        track_cache["tracks"] = tracks
        track_cache["rankings"] = rankings  # ✅ New
        track_cache["last_played_rank"] = None

        logger_step1c.info(f"✅ Cached {len(tracks)} tracks and {len(rankings)} rankings from {filename}")
        return True

    except Exception as e:
        logger_step1c.error(f"❌ Failed to load track file '{filename}': {e}")
        return False

def get_all_rank_entries() -> list[Dict]:
    """
    Return the list of ranking records from track_cache["rankings"].
    Each entry includes rank, genre, decade, and intro.
    """
    return track_cache.get("rankings", [])

def get_track_by_rank(rank: int) -> Optional[Dict]:
    """Return the track dictionary that matches the given rank."""
    try:
        rank = int(rank)
    except (ValueError, TypeError):
        return None

    for track in track_cache["tracks"]:
        try:
            if int(track.get("rank")) == rank:
                return track
        except (ValueError, TypeError):
            continue
    return None

def get_next_track(mode: str = "count-up") -> Optional[Dict]:
    """Return the next track based on current mode and update last_played_rank."""
    tracks = track_cache.get("tracks", [])
    if not tracks:
        return None

    last = track_cache.get("last_played_rank")

    if mode == "count-up":
        next_rank = (last or 0) + 1

    elif mode == "count-down":
        next_rank = (last - 1) if last and last > 1 else len(tracks)

    elif mode == "random":
        track = random.choice(tracks)
        track_cache["last_played_rank"] = track.get("rank")
        return track

    else:
        return None

    track = get_track_by_rank(next_rank)
    if track:
        track_cache["last_played_rank"] = track.get("rank")
    return track
