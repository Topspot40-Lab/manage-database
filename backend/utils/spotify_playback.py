from backend.utils.json_track_loader import load_json_track_file
from backend.services.spotify.track_player import play_spotify_track  # Assumes you have this already

def play_track_by_rank(genre: str, decade: str, rank: int) -> dict:
    """
    Load tracks from JSON, find the one with the given rank, and play it.
    """
    tracks = load_json_track_file(genre, decade)

    track = next((t for t in tracks if t.get("rank") == rank), None)
    if not track:
        raise ValueError(f"No track found with rank {rank} for {genre} in {decade}")

    track_id = track.get("spotifyTrackId")
    if not track_id:
        raise ValueError(f"Track at rank {rank} is missing a Spotify track ID.")

    # Send to Spotify player
    play_spotify_track(track_id)

    return {
        "trackName": track.get("trackName"),
        "artistName": track.get("artistName"),
        "spotifyTrackId": track_id,
        "rank": rank
    }
