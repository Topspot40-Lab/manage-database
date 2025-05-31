import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai
)
from backend.services.track_generator import (
    fetch_and_validate_tracks,
    process_artist,
    build_track_entry,
    build_ranking_entry
)
from shared.filepaths import get_json_path

router = APIRouter()

class TrackRequest(BaseModel):
    category: str = Field(..., description="Decade/category, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"] = Field(..., description="Language used for TTS and descriptions")
    num_tracks: int = Field(..., ge=1, le=50, description="Number of tracks to generate (1–50)")

@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
def generate_track_json(request: TrackRequest):
    logging.info("✅ A. Start generate_track_json")

    # === Step 1: Fetch track names ===
    wrapped = get_top_tracks_from_xai(
        category=request.category,
        genre=request.genre,
        num_tracks=request.num_tracks,
        language=request.language
    )
    if not wrapped or "tracks" not in wrapped:
        raise HTTPException(500, "Failed to retrieve track list from XAI")

    # === Step 2: Fetch enriched descriptions ===
    enriched = get_track_descriptions_from_xai(
        track_data=wrapped,
        language=request.language,
        category=request.category,
        genre=request.genre
    )
    if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(wrapped["tracks"]):
        raise HTTPException(500, "Mismatch or failure in track descriptions")

    # === Step 3: Prepare lists and caches ===
    now = datetime.now().isoformat()
    seen_artists = {}
    description_cache = {}
    artists = []
    tracks = []
    rankings = []

    for base in enriched["tracks"]:
        spotify_data = fetch_and_validate_tracks(base)
        artist_entry = process_artist(
            base, spotify_data, seen_artists, description_cache, request.language
        )
        if artist_entry:
            artists.append(artist_entry)

        tracks.append(build_track_entry(base, request, spotify_data, now))
        rankings.append(build_ranking_entry(base, request, spotify_data, now))

    # === Step 4: Create full JSON ===
    final_json = {
        "core_tables": {
            "genre": [{"genre_name": request.genre}],
            "decade": [{"decade_name": request.category}],
            "artist": artists
        },
        "track_tables": {
            "track": tracks,
            "tracklist": [{
                "name": "TopSpot Autogen",
                "curator": "Mr. Ed",
                "is_official": True,
                "language": request.language[:2].lower(),
                "notes": f"Generated for {request.category} - {request.genre}",
                "created_at": now
            }]
        },
        "ranking_tables": {
            "track_ranking": rankings
        }
    }

    filepath = get_json_path(request.category, request.genre, request.language[:2])
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)
    except Exception as e:
        raise HTTPException(500, f"Failed to write JSON: {e}")

    return {
        "message": "🎉 JSON created successfully",
        "file": str(filepath),
        "version": "v3-simplified",
        "track_count": len(tracks)
    }
