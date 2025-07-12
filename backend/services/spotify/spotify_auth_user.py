import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

_client = None

def get_spotify_user_client() -> spotipy.Spotify:
    global _client
    if _client:
        return _client

    cid = os.getenv("SPOTIPY_CLIENT_ID")
    secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect = os.getenv("SPOTIPY_REDIRECT_URI")
    scope = "user-modify-playback-state user-read-playback-state"

    if not (cid and secret and redirect):
        raise EnvironmentError("Missing Spotify credentials or redirect URI")

    auth_manager = SpotifyOAuth(
        client_id=cid,
        client_secret=secret,
        redirect_uri=redirect,
        scope=scope,
        cache_path=".cache"
    )

    _client = spotipy.Spotify(auth_manager=auth_manager)
    logger.debug("🔐 Spotify user-auth client initialized")
    return _client
