import difflib
from typing import List, Dict, Optional, Tuple
from .auth import get_spotify_client
import logging

logger = logging.getLogger(__name__)

def get_similar_tracks(track_name: str, *, limit: int = 5) -> List[Dict]:
    if not track_name or "[Unknown" in track_name:
        logger.warning("[SPOTIFY] Invalid track name: %s", track_name)
        return []
    sp = get_spotify_client()
    results = sp.search(q=f"track:{track_name}", type="track", limit=limit)
    return [{
        "trackName": item["name"],
        "artistName": item["artists"][0]["name"],
        "spotifyTrackId": item["id"],
        "popularity": item.get("popularity", 0),
        "album_artwork": item["album"]["images"][0]["url"] if item["album"]["images"] else None,
        "yearReleased": item["album"].get("release_date", "")[:4],
    } for item in results["tracks"]["items"]]

def auto_select_best_spotify_match(track_name: str, suggestions: List[Dict]) -> Tuple[Optional[Dict], str]:
    if not suggestions:
        return None, "No suggestions"

    simplified_input = track_name.lower().split("(")[0].strip()
    for s in suggestions:
        candidate = s["trackName"].lower().split("(")[0].strip()
        if simplified_input == candidate:
            return s, "Exact title match"
        if simplified_input in candidate:
            return s, "Partial match"

    names = [s["trackName"] for s in suggestions]
    closest = difflib.get_close_matches(track_name, names, n=1, cutoff=0.6)
    if closest:
        best = next(s for s in suggestions if s["trackName"] == closest[0])
        return best, "Fuzzy match"
    logger.debug("Defaulting to first match for '%s'", track_name)
    return suggestions[0], "First suggestion fallback"
