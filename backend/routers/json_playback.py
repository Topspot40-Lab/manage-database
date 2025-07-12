
from backend.utils.spotify_playback import play_track_by_rank

from fastapi import APIRouter, HTTPException, Query
from backend.services.track_cache import load_tracks_from_file
from backend.config import BASE_DIR
from backend.services.track_cache import track_cache


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
def play_json_track_by_rank_endpoint(genre: str, decade: str, rank: int):
    try:
        track = play_track_by_rank(genre, decade, rank)
        return {"message": f"Playing track at rank {rank}.", "track": track}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
