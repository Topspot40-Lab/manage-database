import os
from dotenv import load_dotenv
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
        results = sp.search(q=query, type="track", limit=1)
        if results["tracks"]["items"]:
            track = results["tracks"]["items"][0]
            return {
                "id": track["id"],
                "artistId": track["artists"][0]["id"],
                "durationMs": track["duration_ms"],
                "popularity": track["popularity"],
                "trackImage": track["album"]["images"][0]["url"] if track["album"]["images"] else None
            }
        else:
            return {}
    except Exception as e:
        print(f"Spotify query error for {track_name} - {artist_name}: {e}")
        return {}
