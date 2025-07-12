from backend.services.spotify.spotify_auth_user import get_spotify_user_client

def play_spotify_track(track_id: str):
    sp = get_spotify_user_client()
    sp.start_playback(uris=[f"spotify:track:{track_id}"])
