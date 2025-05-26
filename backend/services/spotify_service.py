import os
from dotenv import load_dotenv
import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()

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

def get_spotify_data(track_name: str, artist_name: str):
    try:
        sp = get_spotify_client()
        query = f"track:{track_name} artist:{artist_name}"
        results = sp.search(q=query, type="track", limit=3)

        if not results["tracks"]["items"]:
            print(f"❌ No Spotify results for: {track_name} by {artist_name}")
            return {}

        for track in results["tracks"]["items"]:
            result_artist = track["artists"][0]["name"].lower().strip()
            expected_artist = artist_name.lower().strip()

            if result_artist == expected_artist:
                artist_id = track["artists"][0]["id"]

                # 🔍 Fetch artist artwork
                artist_data = sp.artist(artist_id)
                artist_image = artist_data["images"][0]["url"] if artist_data["images"] else None

                return {
                    "id": track["id"],
                    "artistId": artist_id,
                    "durationMs": track["duration_ms"],
                    "popularity": track["popularity"],
                    "trackImage": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                    "artistImage": artist_image
                }

                # 🔍 Add this right here:
            else:
                if result_artist.lower() != expected_artist.lower():
                    logging.warning(f"🪤 Rejected: {result_artist} is not {expected_artist}")
                    # Possibly log a candidate name for human review
                print(f"🪤 Rejected: {result_artist} is not {expected_artist}")

        # 🚫 No valid matches
        print(f"🚫 No matching Spotify artist for: {track_name} by {artist_name}")
        return {}

    except Exception as e:
        print(f"Spotify query error for {track_name} - {artist_name}: {e}")
        return {}
