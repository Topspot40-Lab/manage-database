# backend/routers/json_playback.py

from fastapi import APIRouter, HTTPException
from backend.utils.json_track_loader import load_json_track_file
from backend.utils.spotify_playback import play_track_by_rank

router = APIRouter()

@router.get("/load-json-track-file")
def load_json_track_file_endpoint(genre: str, decade: str):
    try:
        tracks = load_json_track_file(genre, decade)
        return {"message": f"Loaded {len(tracks)} tracks.", "tracks": tracks}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/play-json-track-by-rank")
def play_json_track_by_rank_endpoint(genre: str, decade: str, rank: int):
    try:
        track = play_track_by_rank(genre, decade, rank)
        return {"message": f"Playing track at rank {rank}.", "track": track}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
