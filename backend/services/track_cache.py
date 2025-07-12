from pathlib import Path
import json
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


def load_tracks_from_file(filename: str, full_path: Path) -> bool:
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        track_cache["filename"] = filename
        track_cache["tracks"] = data.get("track_tables", {}).get("track", [])
        track_cache["last_played_rank"] = None  # 🔄 Reset on new file load
        return True
    except Exception as e:
        print(f"❌ Failed to load track file: {e}")
        return False


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
