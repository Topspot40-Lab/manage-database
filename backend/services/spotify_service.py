import os
import logging
from typing import List, Tuple, Optional
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from backend.models.enums import ModeFlag

# from backend.models.enums import ModeFlag  # Or wherever ModeFlag is defined


load_dotenv()


def format_track_display_name(
    track_name: str,
    primary_artist: str,
    featured_artist: str = "",
    mode_flag: int = 0
) -> str:
    """
    Returns a display name for the track based on mode_flag:
    - SOLO: "Song Title - Artist"
    - DUET: "Song Title - Artist & Featured"
    - FEATURED: "Song Title - Artist feat. Featured"
    """
    if mode_flag == 1:  # DUET
        return f"{track_name} - {primary_artist} & {featured_artist}"
    elif mode_flag == 2:  # FEATURED
        return f"{track_name} - {primary_artist} feat. {featured_artist}"
    else:  # SOLO or default
        return f"{track_name} - {primary_artist}"


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


def determine_mode_flag(artist_name: str, artist_list: List[dict]) -> Tuple[ModeFlag, Optional[str]]:
    """
    Determine mode_flag and featured_artist_id based on artist name formatting from XAI and Spotify's artist list.
    - SOLO (0): Solo or established group
    - DUET (1): "and" in name
    - FEATURED (2): "feat." or "ft." in name
    """
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


def get_spotify_data(track_name: str, artist_name: str):
    try:
        sp = get_spotify_client()
        query = f"track:{track_name} artist:{artist_name}"
        results = sp.search(q=query, type="track", limit=3)

        if not results["tracks"]["items"]:
            print(f"❌ No Spotify results for: {track_name} by {artist_name}")
            return {}

        for track in results["tracks"]["items"]:
            artist_list = track["artists"]
            result_artist = artist_list[0]["name"].lower().strip()
            expected_artist = artist_name.lower().strip()

            if result_artist == expected_artist:
                artist_id = artist_list[0]["id"]

                # ✅ Determine mode_flag and featured_artist_id
                mode_flag_enum, featured_artist_id = determine_mode_flag(artist_name, artist_list)

                # ✅ Logging the detection
                logging.info(f"🎙️ mode_flag detected: {mode_flag_enum.name} ({mode_flag_enum.value})")

                # ✅ Fetch artist image
                artist_data = sp.artist(artist_id)
                artist_image = artist_data["images"][0]["url"] if artist_data["images"] else None

                return {
                    "spotify_track_id": track["id"],
                    "artist_id": artist_id,
                    "featured_artist_id": featured_artist_id,
                    "mode_flag": mode_flag_enum.value,  # Send int to DB
                    "duration_ms": track["duration_ms"],
                    "popularity": track["popularity"],
                    "album_artwork": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                    "artist_artwork": artist_image
                }

            else:
                logging.warning(f"🪤 Rejected: {result_artist} is not {expected_artist}")

        print(f"🚫 No matching Spotify artist for: {track_name} by {artist_name}")
        return {}

    except Exception as e:
        print(f"Spotify query error for {track_name} - {artist_name}: {e}")
        return {}


