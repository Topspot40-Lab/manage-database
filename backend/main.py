import os
import sys

# Forcefully add the project root to sys.path so we can find shared/, services/, etc.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Only now import everything else
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from backend.services.spotify_service import get_spotify_data
from backend.services.xai_service import get_top_tracks_from_xai, get_track_descriptions_from_xai
from backend.router_saved_files import router as saved_files_router
from shared.filepaths import get_json_path
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

app = FastAPI()
app.include_router(saved_files_router)

class TrackRequest(BaseModel):
    category: str = Field(..., description="Decade/category, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"] = Field(..., description="Language used for TTS and descriptions")
    num_tracks: int = Field(..., ge=1, le=50, description="Number of tracks to generate (1–50)")

@app.post("/generate-json", summary="Generate JSON from XAI + Spotify")
def generate_track_json(request: TrackRequest):
    # Step 1: Get track list from XAI
    raw_tracks = get_top_tracks_from_xai(
        category=request.category,
        genre=request.genre,
        num_tracks=request.num_tracks,
        language=request.language
    )

    if not raw_tracks:
        raise HTTPException(status_code=500, detail="Failed to retrieve track list from XAI")

    # Step 2: Get intros and details
    descriptions = get_track_descriptions_from_xai(
        track_data=raw_tracks,
        language=request.language,
        category=request.category,
        genre=request.genre
    )

    if not descriptions or len(descriptions) != len(raw_tracks):
        raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

    now = datetime.now().isoformat()
    artists = []
    tracks = []
    rankings = []

    for i, base in enumerate(raw_tracks):
        desc = descriptions[i]
        spotify_data = get_spotify_data(base['trackName'], base['artistName'])

        # Add artist (if new)
        artist_entry = {
            "name": base["artistName"],
            "spotify_artist_id": spotify_data.get("artistId") if spotify_data else None,
            "artist_artwork": None,
            "artist_description": ""
        }
        if artist_entry not in artists:
            artists.append(artist_entry)

        # Add track
        track_entry = {
            "name": base["trackName"],
            "artistName": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "spotify_track_id": spotify_data.get("id") if spotify_data else None,
            "duration_ms": spotify_data.get("durationMs") if spotify_data else None,
            "popularity": spotify_data.get("popularity") if spotify_data else None,
            "album_artwork": spotify_data.get("trackImage") if spotify_data else None,
            "year_released": int(base["yearReleased"]),
            "is_explicit": False,
            "created_at": now
        }
        tracks.append(track_entry)

        rankings.append({
            "trackName": base["trackName"],
            "artistName": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "tracklist": "TopSpot Autogen",
            "rank": base["rank"],
            "intro": desc.get("intro"),
            "detail": desc.get("detail"),
            "description_language": request.language,
            "ranking_date": now[:10]
        })

    final_json = {
        "core_tables": {
            "genre": [{"name": request.genre}],
            "decade": [{"name": request.category}],
            "artist": artists,
            "language": [{"code": request.language[:2].lower(), "name": request.language}],
            "specialty": []
        },
        "track_tables": {
            "track": tracks,
            "tracklist": [
                {
                    "name": "TopSpot Autogen",
                    "curator": "Mr. Ed",
                    "is_official": True,
                    "language": request.language[:2].lower(),
                    "notes": f"Generated for {request.category} - {request.genre}",
                    "created_at": now
                }
            ]
        },
        "ranking_tables": {
            "trackranking": rankings
        }
    }

    filepath = get_json_path(request.category, request.genre, request.language[:2])
    try:
        with open(filepath, "w") as f:
            json.dump(final_json, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write JSON: {e}")

    return {"message": "JSON created successfully", "file": str(filepath)}
