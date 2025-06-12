import os
import logging
from typing import List, Tuple, Optional
from enum import Enum
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pathlib import Path

import re

def clean_track_title(title: str) -> str:
    """Remove any parenthetical like (The Fishin' Song) or (Remastered) from track title."""
    return re.sub(r"\s*\(.*?\)", "", title).strip()


# Load .env from the project root
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

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

    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
    )

# ✅ Determine mode_flag and featured artist
def determine_mode_flag(artist_name: str, artist_list: List[dict]) -> Tuple[ModeFlag, Optional[str]]:
    name_lower = artist_name.lower()

    is_duet = " with " in name_lower
    is_feature = " feat." in name_lower or " featuring " in name_lower

    featured_artist_id = None

    if is_feature and len(artist_list) > 1:
        mode_flag = ModeFlag.FEATURED
        featured_artist_id = artist_list[1]["id"]
    elif is_duet and len(artist_list) > 1:
        mode_flag = ModeFlag.DUET
        featured_artist_id = artist_list[1]["id"]
    else:
        mode_flag = ModeFlag.SOLO

    logger.info(f"[SPOTIFY] Detected mode_flag: {mode_flag.name} ({mode_flag.value})")
    return mode_flag, featured_artist_id

# ✅ Main data fetch function
def get_spotify_data(track_name: str, artist_name: str):
    try:
        sp = get_spotify_client()

        track_name_clean = clean_track_title(track_name)
        query = f"track:{track_name_clean} artist:{artist_name}"

        results = sp.search(q=query, type="track", limit=3)
        track = None

        if results["tracks"]["items"]:
            for t in results["tracks"]["items"]:
                artist_list = t["artists"]
                artist_names = [a["name"].lower() for a in artist_list]
                if artist_name.lower() in artist_names:
                    track = t
                    break

        # 🛠️ Retry if no match
        if not track:
            track = fallback_spotify_search(sp, track_name, artist_name)

        if not track:
            logger.warning(f"[SPOTIFY] No acceptable match for: {track_name} by {artist_name}")
            return {}

        for track in results["tracks"]["items"]:
            artist_list = track["artists"]
            expected_artist = artist_name.lower().strip()

            matched_artist = next(
                (artist for artist in artist_list if expected_artist in artist["name"].lower()), None
            )

            logger.debug(f"[SPOTIFY] expected_artist: '{expected_artist}'")
            logger.debug(f"[SPOTIFY] artist_list: {[a['name'] for a in artist_list]}")

            if matched_artist:
                artist_id = matched_artist["id"]
                mode_flag_enum, _ = determine_mode_flag(artist_name, artist_list)

                artist_data = sp.artist(artist_id)
                artist_image = artist_data["images"][0]["url"] if artist_data["images"] else None

                logger.info(f"[SPOTIFY] Matched track: {track['name']}")

                featured_artist = next(
                    (artist for artist in artist_list if artist["id"] != artist_id),
                    None
                )

                featured_artist_id = featured_artist["id"] if featured_artist else None
                featured_artist_name = featured_artist["name"] if featured_artist else None

                return {
                    "spotify_track_id": track["id"],
                    "artist_id": artist_id,
                    "featured_artist_id": featured_artist_id,
                    "featured_artist_name": featured_artist_name,
                    "mode_flag": mode_flag_enum.value,
                    "duration_ms": track["duration_ms"],
                    "popularity": track["popularity"],
                    "album_artwork": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                    "artist_artwork": artist_image,
                    "artistNameCandidates": artist_list
                }

            else:
                logger.warning(f"[SPOTIFY] Rejected: {[a['name'] for a in artist_list]} does not include '{artist_name}'")

        logger.warning(f"[SPOTIFY] No acceptable match for: {track_name} by {artist_name}")
        return {}

    except Exception as e:
        logger.error(f"[SPOTIFY] Query error for {track_name} - {artist_name}: {e}")
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
