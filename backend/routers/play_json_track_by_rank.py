from fastapi import APIRouter, HTTPException, Query
from backend.services.track_cache import track_cache, get_track_by_rank

from backend.services.spotify.playback import play_spotify_track

router = APIRouter()
@router.post("/play-json-track-by-rank")
def play_json_track_by_rank(rank: int = Query(..., ge=1)):
    tracks = track_cache.get("tracks", [])

    if not tracks:
        raise HTTPException(status_code=400, detail="No JSON file loaded. Use /load-json-track-file first.")

    track = get_track_by_rank(rank)
    if not track:
        raise HTTPException(status_code=404, detail=f"Track with rank {rank} not found.")

    track_id = track.get("spotify_track_id")
    if not track_id:
        raise HTTPException(status_code=400, detail=f"No Spotify track ID for rank {rank}.")

    play_spotify_track(track_id)

    return {
        "message": f"🎵 Playing: {track.get('track_name')} by {track.get('artist_name')}",
        "track_id": track_id
    }

@router.get("/json/current-cache-status")
def get_cache_status():
    return {
        "filename": track_cache.get("filename"),
        "track_count": len(track_cache.get("tracks", []))
    }
