import os
import logging
from typing import Optional
from enum import Enum
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pathlib import Path
import re
import json
import difflib
from backend.utils.json_helpers import normalize_name
from backend.utils.logger_factory import get_step_logger


logger_step3 = get_step_logger("STEP_3")         # General Step 3
logger_spotify = get_step_logger("STEP_3.A")     # Spotify data matching
logger_builder = get_step_logger("STEP_3.B")     # Track entry building

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
def format_track_display_name(track_name: str, featured_artist_name: Optional[str], mode_flag: int) -> str:
    if mode_flag == 0 or not featured_artist_name:
        return track_name
    elif mode_flag == 2:  # DUET
        return f"{track_name} WITH {featured_artist_name}"
    elif mode_flag == 3:  # FEATURED
        return f"{track_name} ft. {featured_artist_name}"
    else:
        return track_name  # fallback or GROUP

# ✅ Authenticate with Spotify
def get_spotify_client():
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise Exception("Spotify credentials are not set in the environment.")

    logger_spotify.debug("🎧 [STEP_3.A] Spotify client authenticated successfully.")
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
    )

def get_spotify_data(track_name: str, artist_name: str):
    logger_spotify.debug("🎧 [STEP_3.A] Calling get_spotify_data")
    try:
        sp = get_spotify_client()

        track_name_clean = clean_track_title(track_name)
        expected_artist_norm = normalize_name(artist_name)

        query = f"{track_name_clean} {artist_name}"
        logger_spotify.debug(f"🔍 [STEP_3.A] Querying Spotify with: '{query}'")

        results = sp.search(q=query, type="track", limit=5)

        # 🧾 Pretty-print full result if DEBUG is enabled
        if logger_spotify.isEnabledFor(logging.DEBUG):
            simplified_items = []

            for item in results["tracks"]["items"]:
                item_copy = item.copy()

                # Remove known top-level noisy fields
                item_copy.pop("available_markets", None)
                item_copy.pop("external_urls", None)
                item_copy.pop("href", None)
                item_copy.pop("uri", None)

                # Trim album fields
                album = item_copy.get("album", {})
                if isinstance(album, dict):
                    album.pop("available_markets", None)
                    album.pop("external_urls", None)
                    album.pop("href", None)
                    album.pop("uri", None)

                # Trim artist fields
                if "artists" in item_copy:
                    for artist in item_copy["artists"]:
                        artist.pop("external_urls", None)
                        artist.pop("href", None)
                        artist.pop("uri", None)

                # Trim album.artist fields
                if "album" in item_copy and isinstance(item_copy["album"], dict):
                    for album_artist in item_copy["album"].get("artists", []):
                        album_artist.pop("external_urls", None)
                        album_artist.pop("href", None)
                        album_artist.pop("uri", None)

                simplified_items.append(item_copy)

            logger_spotify.debug("📦 [STEP_3.A] Raw Spotify results (trimmed):\n" +
                                 json.dumps(simplified_items, indent=2))

        if not results["tracks"]["items"]:
            logger_spotify.warning(f"❌ [STEP_3.A] No results for: '{track_name}' by '{artist_name}'")
            return {}

        for t in results["tracks"]["items"]:
            artist_list = t["artists"]
            for artist in artist_list:
                candidate_name_norm = normalize_name(artist["name"])
                logger_spotify.debug(f"🧪 Comparing: '{expected_artist_norm}' vs '{candidate_name_norm}'")

                if expected_artist_norm == candidate_name_norm:
                    artist_id = artist["id"]
                    artist_data = sp.artist(artist_id)
                    artist_image = artist_data["images"][0]["url"] if artist_data["images"] else None

                    featured_artist = next((a for a in artist_list if a["id"] != artist_id), None)
                    featured_artist_id = featured_artist["id"] if featured_artist else None
                    featured_artist_name = featured_artist["name"] if featured_artist else None

                    logger_spotify.debug(
                        f"✅ [STEP_3.A] Match found: '{t['name']}' by '{artist['name']}' → "
                        f"Track ID: {t['id']}, Duration: {round(t['duration_ms'] / 1000)}s, Popularity: {t['popularity']}"
                    )

                    return {
                        "spotify_track_id": t["id"],
                        "artist_id": artist_id,
                        "featured_artist_id": featured_artist_id,
                        "featured_artist_name": featured_artist_name,
                        "mode_flag": None,
                        "duration_ms": t["duration_ms"],
                        "popularity": t["popularity"],
                        "album_artwork": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                        "artist_artwork": artist_image,
                        "track_name": t["name"],
                        "artist_name": artist["name"],
                        "original_track_name": track_name,
                        "original_artist_name": artist_name,
                        "match_reason": "Normalized name match",
                        "auto_matched": True,
                        "artist_name_candidates": artist_list
                    }

        logger.warning(f"⚠️ [STEP_3.A] No artist match for '{artist_name}' on '{track_name}'. Returning empty.")
        return {}

    except Exception as e:
        logger.error(f"❌ [STEP_3.A] Spotify query error for '{track_name}' by '{artist_name}': {e}")
        return {}

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
    # ---------------------------------------------------------------------------
    # Strict‑artist auto‑match logic
    # ---------------------------------------------------------------------------
    if best_match:
        new_track_name = best_match.get("trackName")
        new_artist_name = best_match.get("artistName")

        # ✅ 1.  Compare normalised artist names
        if normalize_name(new_artist_name) == normalize_name(artist_name):
            logger.debug(
                f"✅ Auto‑match accepted: '{new_track_name}' by '{new_artist_name}'"
            )

            # Grab extra metadata from Spotify
            extra = enrich_track_from_spotify(best_match["spotifyTrackId"])

            # ✅ 2.  Update the bad_track in place
            bad_track.update({
                # ----  canonical / camelCase ----
                "trackName": new_track_name,
                "artistName": new_artist_name,
                "artist_display_name": new_artist_name,
                "track_name": new_track_name,
                "artist_name": new_artist_name,
                "track_display_name": normalize_name(new_track_name),

                "spotify_track_id": best_match["spotifyTrackId"],
                "artist_id": extra.get("artist_id"),
                "spotify_artist_id": extra.get("artist_id"),
                "album_artwork": extra.get("album_artwork"),
                "artist_artwork": extra.get("artist_artwork"),
                "duration_ms": extra.get("duration_ms"),
                "popularity": extra.get("popularity"),
                "match_reason": reason,
                "auto_matched": True,
                "not_on_spotify": False
            })

            # ✅ 3.  Replace the old entry in the list (by rank or by original name)
            original_rank = bad_track.get("rank")
            replaced = False
            for i, t in enumerate(tracks):
                same_rank = original_rank is not None and t.get("rank") == original_rank
                same_title = (t.get("trackName") or t.get("track_name")) == bad_track.get("original_track_name")
                same_artist = (t.get("artistName") or t.get("artist_name")) == bad_track.get("original_artist_name")
                if same_rank or (same_title and same_artist):
                    tracks[i] = bad_track
                    replaced = True
                    logger.debug(f"🔁 Replaced original track at index {i} (rank {t.get('rank')})")
                    break

            # Fallback insert if we couldn’t find the slot
            if not replaced:
                insert_at = (original_rank - 1) if original_rank else len(tracks)
                tracks.insert(insert_at, bad_track)

            log_missing_track_action(
                bad_track,
                "✅ Auto‑replaced with exact‑artist Spotify match",
                best_match,
                category,
                genre
            )
            return True

        # -----------------------------------------------------------------------
        # ⚠️  Artist mismatch → skip auto‑match
        # -----------------------------------------------------------------------
        logger.warning(
            f"❌ Auto‑match skipped — artist mismatch "
            f"(requested '{artist_name}', got '{new_artist_name}')"
        )
        log_missing_track_action(
            bad_track,
            "❌ Skipped auto‑match due to artist mismatch",
            best_match,
            category,
            genre
        )
        return False

    # ❌ Auto-match failed, fallback will be triggered
    print(f"\n❌ Missing track ID for: '{track_name}' by '{artist_name}'")
    return False

def enrich_track_from_spotify(track_id: str) -> dict:
    sp = get_spotify_client()
    data = sp.track(track_id)

    artist_id = data["artists"][0]["id"]
    artist_data = sp.artist(artist_id)

    logger.debug(f"🎨 Fetched artist artwork: {artist_data.get('images')}")

    return {
        "duration_ms": data["duration_ms"],
        "popularity": data["popularity"],
        "album_artwork": data["album"]["images"][0]["url"]
            if data["album"]["images"] else None,
        "artist_id": artist_id,
        "artist_artwork": artist_data["images"][0]["url"]
            if artist_data.get("images") else None,
    }




def enrich_tracks_with_spotify(tracks: list[dict]) -> list[dict]:
    """
    Enrich each XAI-generated track with Spotify metadata using get_spotify_data.
    Adds a 'spotify_data' field to each track dict.
    """
    if not tracks:
        logger_step3.warning("⚠️ [STEP_3] No tracks to enrich.")
        return []

    logger_step3.debug(f"🎧 [STEP_3] Enriching {len(tracks)} track(s) with Spotify metadata…")

    for i, t in enumerate(tracks):
        tn = t.get("trackName") or t.get("track_name")
        an = t.get("artistName") or t.get("artist_name")
        rank = t.get("rank")

        logger_spotify.debug(f"🔄 [STEP_3.A] Rank {rank}: Looking up in Spotify '{tn}' by '{an}'")

        try:
            spotify_data = get_spotify_data(tn, an)

            if spotify_data:
                t["spotify_data"] = spotify_data
                logger_spotify.debug(
                    f"✅ [STEP_3.A] Rank {rank}: Match found → "
                    f"Track ID: {spotify_data.get('spotify_track_id')}, "
                    f"Artist ID: {spotify_data.get('artist_id')}, "
                    f"Duration: {spotify_data.get('duration_ms')}ms, "
                    f"Popularity: {spotify_data.get('popularity')}"
                )
            else:
                logger_spotify.warning(
                    f"❌ [STEP_3.A] Rank {rank}: No match found for '{tn}' by '{an}'"
                )

        except Exception as e:
            logger_step3.error(f"💥 [STEP_3] Rank {rank}: Spotify enrichment failed → {e}")

    match_count = sum(1 for t in tracks if "spotify_data" in t)
    logger_step3.debug(f"🔢 [STEP_3] {match_count} of {len(tracks)} tracks successfully matched with Spotify.")

    return tracks
