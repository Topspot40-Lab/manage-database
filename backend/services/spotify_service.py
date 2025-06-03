import os
import logging
from typing import List, Tuple, Optional
from enum import Enum
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pathlib import Path

# Load .env from the project root
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

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
        return f"{track_name} and {featured_artist_name}"
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

    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
    )

# ✅ Determine mode_flag and featured artist
def determine_mode_flag(artist_name: str, artist_list: List[dict]) -> Tuple[ModeFlag, Optional[str]]:
    name_lower = artist_name.lower()
    is_duet = " and " in name_lower
    is_feature = " ft. " in name_lower or "feat." in name_lower
    is_group = "&" in artist_name

    mode_flag = ModeFlag.SOLO
    featured_artist_id = None

    if len(artist_list) > 1:
        second_artist = artist_list[1]
        featured_artist_id = second_artist["id"]

        if is_feature:
            mode_flag = ModeFlag.FEATURED
        elif is_duet:
            mode_flag = ModeFlag.DUET
        elif is_group:
            mode_flag = ModeFlag.SOLO
    else:
        if is_duet or is_feature:
            logging.warning(
                f"❗ '{artist_name}' suggests duet or feature, but only one Spotify artist found: {[a['name'] for a in artist_list]}"
            )
        mode_flag = ModeFlag.SOLO
        featured_artist_id = None

    logging.info(f"🎙️ Detected mode_flag: {mode_flag.name} ({mode_flag.value})")
    return mode_flag, featured_artist_id

# ✅ Main data fetch function
def get_spotify_data(track_name: str, artist_name: str):
    try:
        sp = get_spotify_client()
        query = f"track:{track_name} artist:{artist_name}"
        results = sp.search(q=query, type="track", limit=3)

        if not results["tracks"]["items"]:
            logging.warning(f"❌ No Spotify results for: {track_name} by {artist_name}")
            return {}

        for track in results["tracks"]["items"]:
            artist_list = track["artists"]
            result_artist = artist_list[0]["name"].lower().strip()
            expected_artist = artist_name.lower().strip()

            logging.debug("🎧 Checking Spotify match:")
            logging.debug(f"    🟢 result_artist:   '{result_artist}'")
            logging.debug(f"    🟡 expected_artist: '{expected_artist}'")
            logging.debug(f"    🎭 Full artist list: {[a['name'] for a in artist_list]}")

            if expected_artist in result_artist or result_artist in expected_artist:
                artist_id = artist_list[0]["id"]
                mode_flag_enum, featured_artist_id = determine_mode_flag(artist_name, artist_list)

                artist_data = sp.artist(artist_id)
                artist_image = artist_data["images"][0]["url"] if artist_data["images"] else None

                logging.info(f"✅ Matched Spotify track: {track['name']}")

                return {
                    "spotify_track_id": track["id"],
                    "artist_id": artist_id,
                    "featured_artist_id": featured_artist_id,
                    "featured_artist_name": artist_list[1]["name"] if len(artist_list) > 1 else None,
                    "mode_flag": mode_flag_enum.value,
                    "duration_ms": track["duration_ms"],
                    "popularity": track["popularity"],
                    "album_artwork": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                    "artist_artwork": artist_image,
                    "artistNameCandidates": artist_list
                }

            else:
                logging.warning(f"🪤 Rejected: '{result_artist}' is not a match for '{expected_artist}'")

        logging.warning(f"🚫 No acceptable Spotify match found for: {track_name} by {artist_name}")
        return {}

    except Exception as e:
        logging.error(f"Spotify query error for {track_name} - {artist_name}: {e}")
        return {}
