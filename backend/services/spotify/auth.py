import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth


logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

_client = None
def get_spotify_client() -> spotipy.Spotify:
    global _client
    if _client:
        return _client

    cid = os.getenv("SPOTIPY_CLIENT_ID")
    secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = "http://127.0.0.1:8000/auth/callback"

    _client = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=cid,
        client_secret=secret,
        redirect_uri=redirect_uri,
        scope="user-modify-playback-state,user-read-playback-state"
    ))

    logger.info("🎧 Spotify client with OAuth ready")
    return _client
