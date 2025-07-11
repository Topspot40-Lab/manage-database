# backend/services/spotify/missing_log.py

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend.services.spotify.search import get_similar_tracks, auto_select_best_spotify_match
from backend.services.spotify.enrich import enrich_track_from_spotify
from backend.services.spotify.helpers import format_artist_display_name, ModeFlag
from backend.utils.json_helpers import normalize_name

logger = logging.getLogger(__name__)


def log_missing_track_action(
    original: Dict,
    action: str,
    replacement: Optional[Dict] = None,
    *,
    category: str = "unknown",
    genre: str = "unknown"
) -> None:
    """Append a human-readable record of how a missing track was resolved."""
    os.makedirs("logs", exist_ok=True)
    file_path = Path("logs") / f"missing_tracks_{category.replace(' ', '_')}_{genre.replace(' ', '_')}.txt"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with file_path.open("a", encoding="utf-8") as f:
        f.write("=" * 40 + "\n")
        f.write(f"🕒 {timestamp}\n")
        track_name = original.get("trackName") or original.get("track_name", "[Unknown Track]")
        artist_name = original.get("artistName") or original.get("artist_name", "[Unknown Artist]")
        f.write(f"❌ Original Track: {track_name} by {artist_name}\n")
        f.write(f"🛠️ Action Taken: {action}\n")

        if replacement:
            rep_name = replacement.get("trackName", "[Unknown Track]")
            rep_artist = replacement.get("artistName", "[Unknown Artist]")
            f.write(f"✅ Replacement Track: {rep_name} by {rep_artist}\n")
            spotify_id = replacement.get("spotifyTrackId") or replacement.get("spotify_track_id")
            if spotify_id:
                f.write(f"🔗 Spotify URL: https://open.spotify.com/track/{spotify_id}\n")
            if replacement.get("popularity"):
                f.write(f"🌟 Popularity: {replacement['popularity']}\n")
        f.write("\n")


def reassign_ranks(tracks: List[Dict]) -> None:
    """Ensure tracks are ranked 1.N after any changes."""
    for i, track in enumerate(tracks, 1):
        track["rank"] = i


def handle_missing_track(bad_track: Dict, tracks: List[Dict]) -> bool:

    """
    Attempt to resolve a missing track by using Spotify suggestions.
    If matched, update the track in-place and reinsert it into the list.
    """
    track_name = bad_track.get("trackName") or bad_track.get("track_name", "[Unknown Track]")
    artist_name = bad_track.get("artistName") or bad_track.get("artist_name", "[Unknown Artist]")

    if not track_name.strip() or not artist_name.strip():
        logger.warning(f"❌ Cannot handle missing track — missing name/artist: {bad_track}")
        print("\n❌ Cannot suggest replacements — track or artist name missing.\n")
        return False

    bad_track["original_track_name"] = track_name
    bad_track["original_artist_name"] = artist_name

    # 🚀 Step 1: Try to find Spotify suggestions
    suggestions = get_similar_tracks(track_name)
    best_match, reason = auto_select_best_spotify_match(track_name, suggestions)

    category = bad_track.get("decade", "unknown")
    genre = bad_track.get("genre", "unknown")

    if best_match:
        print(f"✅ Auto-matched '{track_name}' → '{best_match.get('trackName')}' ({reason})")
        extra = enrich_track_from_spotify(best_match["spotifyTrackId"])

        new_track_name = best_match["trackName"]
        new_artist_name = best_match["artistName"]

        bad_track.update({
            "trackName": new_track_name,
            "artistName": new_artist_name,
            "track_name": new_track_name,
            "artist_name": new_artist_name,
            "artist_display_name": format_artist_display_name(
                normalize_name(new_artist_name),
                None,
                ModeFlag.SOLO
            ),
            "spotify_track_id": best_match["spotifyTrackId"],
            "album_artwork": extra["album_artwork"],
            "artist_id": extra["artist_id"],
            "artist_artwork": extra["artist_artwork"],
            "duration_ms": extra["duration_ms"],
            "popularity": extra["popularity"],
            "match_reason": reason,
            "auto_matched": True
        })

        original_rank = bad_track.get("rank")
        replaced = False

        for i, t in enumerate(tracks):
            t_rank = t.get("rank")
            t_name = t.get("trackName") or t.get("track_name")
            t_artist = t.get("artistName") or t.get("artist_name")
            if (
                t_name == bad_track["original_track_name"]
                and t_artist == bad_track["original_artist_name"]
            ) or (original_rank is not None and t_rank == original_rank):
                tracks[i] = bad_track
                replaced = True
                logger.debug(f"🔁 Replaced original track at index {i} (rank {t_rank})")
                break

        if not replaced and original_rank is not None:
            insert_index = original_rank - 1
            if insert_index < len(tracks):
                logger.warning(f"⚠️ Could not find match by name/rank — inserting at index {insert_index}")
                tracks.insert(insert_index, bad_track)
            else:
                logger.warning(f"📌 Rank index too high ({insert_index}) — appending at end")
                tracks.append(bad_track)
        elif not replaced:
            logger.warning(f"📌 No rank found — appending track to end")
            tracks.append(bad_track)

        log_missing_track_action(
            bad_track,
            f"✅ Auto-replaced with Spotify suggestion ({reason})",
            best_match,
            category=category,
            genre=genre
        )

        return True

    print(f"\n❌ No suitable match found for: '{track_name}' by '{artist_name}'")
    return False

