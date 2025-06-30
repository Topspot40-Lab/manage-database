import os
import logging
from typing import Optional
from enum import Enum
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pathlib import Path
import re
import difflib
from backend.utils.json_helpers import normalize_name

print("📄 spotify_service.py loaded from:", os.path.abspath(__file__))

# Load .env from the project root
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

def auto_select_best_spotify_match(track_name: str, suggestions: list[dict]) -> tuple[Optional[dict], str]:
    """
    Attempt to auto-select the best Spotify match from suggestions.

    Returns:
        - best_match (dict) or None
        - reason (str) describing match logic
    """
    if not suggestions:
        return None, "No Spotify suggestions available"

    simplified_input = track_name.lower().split("(")[0].strip()

    for suggestion in suggestions:
        name = suggestion.get("trackName", "").lower()
        simplified_name = name.split("(")[0].strip()

        if simplified_input == simplified_name:
            logger.info(f"🎯 Exact simplified match: '{simplified_input}' == '{simplified_name}'")
            return suggestion, "Exact match after simplification"

        if simplified_input in simplified_name:
            logger.info(f"🧠 Partial simplified match: '{simplified_input}' in '{simplified_name}'")
            return suggestion, "Partial match after simplification"

    suggestion_names = [s.get("trackName") for s in suggestions if "trackName" in s]
    closest_matches = difflib.get_close_matches(track_name, suggestion_names, n=1, cutoff=0.6)

    if closest_matches:
        selected = next((s for s in suggestions if s.get("trackName") == closest_matches[0]), None)
        if selected:
            logger.info(f"🌀 Fuzzy match selected: '{closest_matches[0]}' for '{track_name}'")
            return selected, "Fuzzy match (difflib)"

    fallback = suggestions[0]
    logger.warning(f"⚠️ No strong match for '{track_name}'. Falling back to: '{fallback.get('trackName')}'")
    return fallback, "Fallback to top Spotify suggestion"


def clean_track_title(title: str) -> str:
    """Remove any parenthetical like (The Fishin' Song) or (Remastered) from track title."""
    return re.sub(r"\s*\(.*?\)", "", title).strip()



# ✅ Define ModeFlag enum locally if not imported
class ModeFlag(Enum):
    SOLO = 0
    GROUP = 1
    DUET = 2
    FEATURED = 3

# ✅ Format the track display name based on mode_flag
def format_artist_display_name(
    main_artist_name: str,
    featured_artist_name: Optional[str],
    mode_flag: int
) -> str:
    if mode_flag == ModeFlag.DUET.value and featured_artist_name:
        return f"{main_artist_name} WITH {featured_artist_name} (Duet)"
    if mode_flag == ModeFlag.FEATURED.value and featured_artist_name:
        return f"{main_artist_name} feat. {featured_artist_name}"
    return main_artist_name  # SOLO or GROUP

# ✅ Authenticate with Spotify
def get_spotify_client():
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise Exception("Spotify credentials are not set in the environment.")

    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
    )
def fallback_spotify_search(sp, track_name, artist_name):
    logger.info(f"[SPOTIFY][RETRY] Trying fallback search: '{track_name} {artist_name}'")

    fallback_query = f"{track_name} {artist_name}"
    results = sp.search(q=fallback_query, type="track", limit=5)

    for track in results["tracks"]["items"]:
        track_artist_names = [a["name"].lower() for a in track["artists"]]
        if artist_name.lower() in track_artist_names:
            logger.info(f"[SPOTIFY][RETRY] Matched in fallback: {track['name']} by {track_artist_names}")
            return track

    logger.warning(f"[SPOTIFY][RETRY] No match in fallback search.")
    return None

def get_similar_tracks(track_name: str, limit=5):
    if not track_name or "[Unknown" in track_name:
        logger.warning(f"[SPOTIFY][SUGGESTIONS] Skipping suggestions for invalid track_name: {track_name}")
        return []

    sp = get_spotify_client()
    results = sp.search(q=f"track:{track_name}", type="track", limit=limit)

    suggestions = []
    for item in results["tracks"]["items"]:
        suggestions.append({
            "trackName": item["name"],
            "artistName": item["artists"][0]["name"],
            "spotifyTrackId": item["id"],
            "popularity": item.get("popularity", 0),
            "album_artwork": item["album"]["images"][0]["url"] if item["album"]["images"] else None,
            "yearReleased": item["album"].get("release_date", "")[:4]  # Gets the year only
        })
    return suggestions





def prompt_user_for_replacement(track_name, artist_name, suggestions, spare_tracks=None):
    print(f"\n🎯 Missing track: '{track_name}' by {artist_name}")
    print("Here are possible replacements:")

    # Show Spotify suggestions
    for idx, item in enumerate(suggestions, 1):
        suggestion_track = item.get("trackName", "[Unknown]")
        suggestion_artist = item.get("artistName", "[Unknown]")
        year_released = item.get("yearReleased", "????")
        popularity = item.get("popularity", "N/A")
        print(f"[{idx}] {suggestion_track} – {suggestion_artist} ({year_released}) — Popularity: {popularity}")

    # Show spare tracks if available
    if spare_tracks:
        print("\n🎵 Spare Tracks:")
        for s_idx, item in enumerate(spare_tracks, 1):
            spare_track = item.get("trackName", "[Unknown]")
            spare_artist = item.get("artistName", "[Unknown]")
            year_released = item.get("yearReleased", "????")
            print(f"[S{s_idx}] {spare_track} – {spare_artist} ({year_released})")

    print("[s] Skip this track")

    while True:
        choice = input("📝 Choose a Spotify [1–{}], a Spare [S1–S#], or [s]kip: ".format(len(suggestions))).strip().lower()

        if choice == 's':
            return None

        if choice.isdigit():
            choice_int = int(choice)
            if 1 <= choice_int <= len(suggestions):
                return suggestions[choice_int - 1]

        if choice.startswith('s') and len(choice) > 1 and choice[1:].isdigit():
            spare_index = int(choice[1:]) - 1
            if spare_tracks and 0 <= spare_index < len(spare_tracks):
                return spare_tracks[spare_index]

        print("❗ Invalid input.")

def choose_spare_track(spare_tracks):
    import pprint
    print("\n🧪 DEBUG: Spare Track Sample:")
    pprint.pprint(spare_tracks[:3])  # View first few entries

    print("\n🎒 Spare Tracks:")
    for idx, track in enumerate(spare_tracks, 1):
        track_name = track.get("trackName") or track.get("track_name", "[Unknown]")
        artist_name = track.get("artistName") or track.get("artist_name", "[Unknown]")
        popularity = track.get("popularity")
        spotify_id = track.get("spotifyTrackId") or track.get("spotify_track_id")

        line = f"[{idx}] {track_name} by {artist_name}"
        if popularity:
            line += f" (Popularity: {popularity})"
        print(line)
        if spotify_id:
            print(f"    🔗 https://open.spotify.com/track/{spotify_id}")

    while True:
        choice = input(f"Choose spare [1–{len(spare_tracks)}] or [s]kip: ").strip().lower()
        if choice == 's':
            return None
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(spare_tracks):
                return spare_tracks.pop(index - 1)
        print("❗ Invalid choice. Please try again.")

def reassign_ranks(tracks):
    for i, track in enumerate(tracks, 1):
        track["rank"] = i
def log_missing_track_action(original_track, action, replacement=None, category=None, genre=None):
    import os
    from datetime import datetime

    # ✅ Make sure the logs directory exists
    os.makedirs("logs", exist_ok=True)

    # 🏷️ Safe file naming
    safe_category = category.replace(" ", "_") if category else "unknown"
    safe_genre = genre.replace(" ", "_") if genre else "unknown"
    log_file = f"logs/missing_tracks_{safe_category}_{safe_genre}.txt"

    # 🕒 Write log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("=========================================\n")
        f.write(f"🕒 {timestamp}\n")
        track_name = original_track.get("trackName") or original_track.get("track_name") or "[Unknown Track]"
        artist_name = original_track.get("artistName") or original_track.get("artist_name") or "[Unknown Artist]"
        f.write(f"❌ Original Track: {track_name} by {artist_name}\n")

        f.write(f"🛠️ Action Taken: {action}\n")

        if replacement:
            f.write(f"✅ Replacement Track: {replacement['trackName']} by {replacement['artistName']}\n")
            # ✅ Handle both camelCase and snake_case
            spotify_id = replacement.get("spotifyTrackId") or replacement.get("spotify_track_id")
            if spotify_id:
                f.write(f"🔗 Spotify URL: https://open.spotify.com/track/{spotify_id}\n")
            if replacement.get("popularity"):
                f.write(f"🌟 Popularity: {replacement['popularity']}\n")

        f.write("\n")

def handle_missing_track(bad_track, tracks, spare_tracks) -> bool:
    track_name = bad_track.get("trackName") or bad_track.get("track_name") or "[Unknown Track]"
    artist_name = bad_track.get("artistName") or bad_track.get("artist_name") or "[Unknown Artist]"

    if not track_name.strip() or not artist_name.strip():
        logger.warning(f"❌ Cannot handle missing track — missing name/artist: {bad_track}")
        print(f"\n❌ Cannot suggest replacements — track or artist name missing.\n")
        return False

    # 📝 Preserve original name/artist for fallback matching
    bad_track["original_track_name"] = track_name
    bad_track["original_artist_name"] = artist_name

    # 🚀 Try auto-match
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
            # ✅ For ranking_table and diagnostics
            "trackName": new_track_name,
            "artistName": new_artist_name,

            # ✅ For track_table consistency
            "track_name": new_track_name,
            "artist_name": new_artist_name,
            "artist_display_name": format_artist_display_name(
                normalize_name(new_track_name),
                None,
                0  # ModeFlag.SOLO — adjust if you later re-evaluate mode
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
        # ✅ Try to replace original track
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

        # 🧩 Fallback: reinsert at index based on rank
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
            category,
            genre
        )

        return True

    # ❌ Auto-match failed, fallback will be triggered
    print(f"\n❌ Missing track ID for: '{track_name}' by '{artist_name}'")
    return False

def enrich_track_from_spotify(track_id: str) -> dict:
    sp = get_spotify_client()
    data = sp.track(track_id)
    artist_id = data["artists"][0]["id"]
    artist_info = sp.artist(artist_id)

    logger.debug(
        f"🎨 Retrieved artist_artwork for {artist_info.get('name')}: {artist_info['images'][0]['url'] if artist_info.get('images') else '❌ None'}")

    return {
        "duration_ms": data["duration_ms"],
        "popularity": data["popularity"],
        "album_artwork": data["album"]["images"][0]["url"] if data["album"]["images"] else None,
        "artist_id": artist_id,
        "artist_artwork": artist_info["images"][0]["url"] if artist_info.get("images") else None,
    }
