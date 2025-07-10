import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

_client = None

def get_spotify_client() -> spotipy.Spotify:
    global _client
    if _client:
        return _client

    cid = os.getenv("SPOTIPY_CLIENT_ID")
    secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    if not (cid and secret):
        raise EnvironmentError("Spotify creds not set")

    _client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(cid, secret))
    logger.debug("🔐 Spotify client initialized")
    return _client
