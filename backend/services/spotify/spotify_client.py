import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)

# Load .env from the root of the project
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# Read Spotify credentials
cid = os.getenv("SPOTIPY_CLIENT_ID")
secret = os.getenv("SPOTIPY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")  # Must be set in your Spotify app config

if not (cid and secret and redirect_uri):
    raise EnvironmentError("Missing Spotify credentials in environment")

# Initialize Spotipy client with user authentication
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=cid,
    client_secret=secret,
    redirect_uri=redirect_uri,
    scope="user-modify-playback-state user-read-playback-state"
))
