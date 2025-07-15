from pathlib import Path
import random
from typing import Optional, Dict, Any

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 Track Cache — Loaded from JSON
# ─────────────────────────────────────────────────────────────────────────────
track_cache: Dict[str, Any] = {
    "filename": None,
    "tracks": [],
    "last_played_rank": None
}

from backend.utils.json_helpers import load_json
from backend.utils.logger_factory import get_step_logger

logger_step1c = get_step_logger("STEP_1.C")

def load_tracks_from_file(filename: str, full_path: Path) -> bool:
    try:
        data = load_json(file_path=full_path)  # Now uses logging
        # tracks = data.get("track_tables", {}).get("track", [])
        tracks = data.get("track_tables", {}).get("track", [])  # ✅ Full track data with spotify_track_id

        track_cache["filename"] = filename
        track_cache["tracks"] = tracks
        track_cache["last_played_rank"] = None

        logger_step1c.info(f"✅ Cached {len(tracks)} tracks from {filename}")
        return True

    except Exception as e:
        logger_step1c.error(f"❌ Failed to load track file '{filename}': {e}")
        return False

def get_all_rankings() -> list[Dict]:
    """
    Return the list of ranking records from track_cache["tracks"].
    Each record must include rank, decade, genre, and intro.
    """
    return track_cache.get("tracks", [])


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
