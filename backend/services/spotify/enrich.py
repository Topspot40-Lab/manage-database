from typing import Dict
from .auth import get_spotify_client

def enrich_track_from_spotify(track_id: str) -> Dict:
    sp = get_spotify_client()
    data = sp.track(track_id)
    artist_id = data["artists"][0]["id"]
    artist_info = sp.artist(artist_id)

    return {
        "duration_ms": data["duration_ms"],
        "popularity": data.get("popularity"),
        "album_artwork": data["album"]["images"][0]["url"] if data["album"]["images"] else None,
        "album_name": data["album"]["name"],  # ✅ Add album name from Spotify
        "artist_id": artist_id,
        "artist_artwork": artist_info["images"][0]["url"] if artist_info.get("images") else None,
    }
