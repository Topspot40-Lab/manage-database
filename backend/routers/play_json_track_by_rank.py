from fastapi import APIRouter, HTTPException, Query
from backend.services.track_cache import track_cache, get_track_by_rank
from backend.services.track_cache import load_tracks_from_file
from backend.services.spotify.playback import play_spotify_track
from backend.config import BASE_DIR


router = APIRouter()
@router.get("/load-json-track-file")
def load_json_track_file_endpoint(
    genre: str = Query(...),
    decade: str = Query(...)
):
    genre = genre.lower()
    decade = decade.lower()
    filename = f"{decade}_{genre}_en.json"

    file_path = (
        BASE_DIR / "data/json_files/genredecade" / decade / filename
    )

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    success = load_tracks_from_file(filename, file_path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to load file.")

    return {
        "message": f"✅ Loaded file: {filename}",
        "track_count": len(track_cache.get("tracks", [])),
        "filename": filename,
        "tracks": track_cache["tracks"]  # ✅ full content
    }


@router.post("/play-json-track-by-rank")
def play_json_track_by_rank(rank: int = Query(..., ge=1)):
    print("********   Calling Play-json-track Endpoint")
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

@router.get("/current-cache-status")
def get_cache_status():
    return {
        "filename": track_cache.get("filename"),
        "track_count": len(track_cache.get("tracks", []))
    }
