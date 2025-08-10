import os
import logging
from typing import Optional
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pathlib import Path
import re
import difflib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.utils.json_helpers import normalize_name
from backend.utils.logger_factory import get_step_logger


logger_step3 = get_step_logger("STEP_3")         # General Step 3
logger_spotify = get_step_logger("STEP_3.A")     # Spotify data matching
logger_builder = get_step_logger("STEP_3.B")     # Track entry building

# Load .env from the project root
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

# Allow overriding market via env, default to US to reduce noise/duplicates
SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "US")


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


# ✅ Authenticate with Spotify (robust: retries + timeout)
def get_spotify_client() -> spotipy.Spotify:
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise Exception("Spotify credentials are not set in the environment.")

    # Session with retry & backoff (handles 429/5xx + transient timeouts)
    session = requests.Session()
    retry = Retry(
        total=3, connect=3, read=3,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret),
        requests_session=session,
        requests_timeout=10,  # bump from default ~5s
    )

    logger_spotify.debug("🎧 [STEP_3.A] Spotify client authenticated (retry+timeout enabled).")
    return sp


def get_spotify_data(track_name: str, artist_name: str):
    logger_spotify.debug("🎧 [STEP_3.A] Calling get_spotify_data")
    try:
        sp = get_spotify_client()

        track_name_clean = clean_track_title(track_name)
        # Build expected artist names set (normalized)
        raw_artist = (artist_name or "").strip()

        # Split common collaboration connectors (en/es)
        CONNECTORS = [
            r"\s+feat\.\s+", r"\s+ft\.\s+", r"\s+featuring\s+",
            r"\s+with\s+", r"\s+con\s+", r"\s+y\s+", r"\s*&\s*"
        ]
        parts = [raw_artist]
        for pat in CONNECTORS:
            segs = re.split(pat, raw_artist, flags=re.IGNORECASE)
            if len(segs) > 1:
                parts = [segs[0].strip(), " & ".join(s.strip() for s in segs[1:] if s.strip())]
                break  # only split once on the first connector we find

        # main first, then the “other side”, then original (for completeness)
        artist_candidates = [p for p in parts if p] or [raw_artist]
        expected_names_norm = {normalize_name(p) for p in artist_candidates if p}

        def _search_and_pick(q_track: str, q_artist: str | None, reason_hint: str):
            q = f"{q_track} {q_artist}" if q_artist else q_track
            logger_spotify.debug(f"🔍 [STEP_3.A] Querying Spotify with: '{q}' (market={SPOTIFY_MARKET})")
            results = sp.search(q=q, type="track", limit=5, market=SPOTIFY_MARKET)

            if not results["tracks"]["items"]:
                logger_spotify.debug(f"🙅 [STEP_3.A] No items for query: '{q}'")
                return None, None

            # 1) Exact normalized artist name match on any credited artist
            for it in results["tracks"]["items"]:
                for art in it["artists"]:
                    cand = normalize_name(art["name"])
                    if cand in expected_names_norm:
                        return it, f"{reason_hint}: artist exact normalized match"

            # 2) If we didn’t require an artist (track-only search), allow title-only match
            if q_artist is None:
                tn_norm = normalize_name(track_name_clean)
                for it in results["tracks"]["items"]:
                    if normalize_name(it["name"]) == tn_norm:
                        return it, f"{reason_hint}: title-only normalized match"

            # 3) Fallback: take first result (often correct when query is specific)
            return results["tracks"]["items"][0], f"{reason_hint}: first result fallback"

        # Try in order:
        item, why = _search_and_pick(track_name_clean, artist_candidates[0] if artist_candidates else None, "main")
        if not item and len(artist_candidates) > 1:
            item, why = _search_and_pick(track_name_clean, artist_candidates[1], "collab-side")
        if not item:
            item, why = _search_and_pick(track_name_clean, None, "track-only")

        if not item:
            logger_spotify.warning(f"❌ [STEP_3.A] No results for: '{track_name}' by '{artist_name}'")
            return {}

        # Choose primary artist as the first credited one on the item
        primary_artist = item["artists"][0]
        artist_id = primary_artist["id"]
        artist_data = sp.artist(artist_id)
        artist_image = artist_data["images"][0]["url"] if artist_data["images"] else None

        # Pick a featured artist if there is more than one
        featured_artist = next((a for a in item["artists"] if a["id"] != artist_id), None)
        featured_artist_id = featured_artist["id"] if featured_artist else None
        featured_artist_name = featured_artist["name"] if featured_artist else None

        logger_spotify.debug(
            f"✅ [STEP_3.A] Match: '{item['name']}' by '{primary_artist['name']}' "
            f"→ Track ID: {item['id']}, Pop: {item['popularity']} ({why})"
        )
        return {
            "spotify_track_id": item["id"],
            "artist_id": artist_id,
            "featured_artist_id": featured_artist_id,
            "featured_artist_name": featured_artist_name,
            "mode_flag": None,
            "duration_ms": item["duration_ms"],
            "popularity": item["popularity"],
            "album_name": item["album"]["name"],
            "album_artwork": item["album"]["images"][0]["url"] if item["album"]["images"] else None,
            "artist_artwork": artist_image,
            "track_name": item["name"],
            "artist_name": primary_artist["name"],
            "original_track_name": track_name,
            "original_artist_name": artist_name,
            "match_reason": why,
            "auto_matched": True,
            "artist_name_candidates": item["artists"],
        }

    except Exception as e:
        logger_spotify.error(f"❌ [STEP_3.A] Spotify query error for '{track_name}' by '{artist_name}': {e}")
        return {}


def fallback_spotify_search(sp, track_name, artist_name):
    logger.info(f"[SPOTIFY][RETRY] Trying fallback search: '{track_name} {artist_name}'")
    fallback_query = f"{track_name} {artist_name}"
    results = sp.search(q=fallback_query, type="track", limit=5, market=SPOTIFY_MARKET)

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
    results = sp.search(q=f"track:{track_name}", type="track", limit=limit, market=SPOTIFY_MARKET)

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
    safe_category = (category or "unknown").replace(" ", "_")
    safe_genre = (genre or "unknown").replace(" ", "_")
    log_file = f"logs/missing_tracks_{safe_category}_{safe_genre}.txt"

    # 🕒 Write log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("=========================================\n")
        f.write(f"🕒 {timestamp}\n")

        track_name = (
            original_track.get("trackName")
            or original_track.get("track_name")
            or "[Unknown Track]"
        )
        artist_name = (
            original_track.get("artistName")
            or original_track.get("artist_name")
            or "[Unknown Artist]"
        )
        f.write(f"❌ Original Track: {track_name} by {artist_name}\n")

        f.write(f"🛠️ Action Taken: {action}\n")

        if replacement:
            rep_track = replacement.get("trackName") or replacement.get("track_name") or "[Unknown]"
            rep_artist = replacement.get("artistName") or replacement.get("artist_name") or "[Unknown]"
            f.write(f"✅ Replacement Track: {rep_track} by {rep_artist}\n")

            # ✅ Handle both camelCase and snake_case
            spotify_id = replacement.get("spotifyTrackId") or replacement.get("spotify_track_id")
            if spotify_id:
                f.write(f"🔗 Spotify URL: https://open.spotify.com/track/{spotify_id}\n")
            if replacement.get("popularity"):
                f.write(f"🌟 Popularity: {replacement['popularity']}\n")

        f.write("\n")

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


def enrich_tracks_with_spotify(tracks: list[dict], is_test_mode: bool = False) -> list[dict]:
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

        if is_test_mode:
            logger_spotify.debug(f"🧪 [STEP_3.A] TEST MODE → Enriching Rank {rank}: '{tn}' by '{an}'")
        else:
            logger_spotify.debug(f"🔄 [STEP_3.A] Enriching Rank {rank}: '{tn}' by '{an}'")

        try:
            spotify_data = get_spotify_data(tn, an)

            if spotify_data:
                t["spotify_data"] = spotify_data

                # ✅ Unpack to top-level fields
                t["spotify_track_id"] = spotify_data.get("spotify_track_id")
                t["spotify_artist_id"] = spotify_data.get("artist_id")
                t["duration_ms"] = spotify_data.get("duration_ms")
                t["album_name"] = spotify_data.get("album_name")
                t["track_image"] = spotify_data.get("album_artwork")
                t["artist_artwork"] = spotify_data.get("artist_artwork")
                t["popularity"] = spotify_data.get("popularity")
                t["featured_artist_name"] = spotify_data.get("featured_artist_name")
                t["featured_artist_id"] = spotify_data.get("featured_artist_id")
                t["mode_flag"] = t.get("mode_flag", "unknown")

                logger_spotify.debug(
                    f"✅ [STEP_3.A] Rank {rank}: Unpacked and enriched → "
                    f"Track ID: {t.get('spotify_track_id')}, "
                    f"Artist ID: {t.get('spotify_artist_id')}"
                )

            else:
                logger_spotify.warning(
                    f"❌ [STEP_3.A] Rank {rank}: No match found for '{tn}' by '{an}'")

        except Exception as e:
            logger_step3.error(f"💥 [STEP_3] Rank {rank}: Spotify enrichment failed → {e}")

    match_count = sum(1 for t in tracks if "spotify_data" in t)
    logger_step3.debug(f"🔢 [STEP_3] {match_count} of {len(tracks)} tracks successfully matched with Spotify.")

    # 🧾 Optional summary log for every track
    for t in tracks:
        rank = t.get("rank")
        tn = t.get("trackName") or t.get("track_name")
        an = t.get("artistName") or t.get("artist_name")
        sd = t.get("spotify_data", {})

        logger_spotify.debug(
            f"🎵 Rank {rank}: '{tn}' by '{an}'\n"
            f"   • Track ID: {sd.get('spotify_track_id', '❌')}\n"
            f"   • Artist ID: {sd.get('artist_id', '❌')}\n"
            f"   • Duration: {sd.get('duration_ms', '❌')} ms\n"
            f"   • Popularity: {sd.get('popularity', '❌')}\n"
            f"   • Album Art: {'✔️' if sd.get('album_artwork') else '❌'}\n"
            f"   • Artist Art: {'✔️' if sd.get('artist_artwork') else '❌'}"
        )

    return tracks
