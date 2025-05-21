# backend/routers/generate_json.py
import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Path, Depends
from pydantic import BaseModel, Field
from typing import Literal
from sqlmodel import Session, select

from backend.services.spotify_service import get_spotify_data
from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai,
    get_artist_description
)

from backend.database import get_db
from models.dbmodels import Genre, Decade, Artist, Track, TrackRanking, DecadeGenre, Tracklist
from shared.filepaths import get_json_path

print("🧩 generate_json.py is now the OFFICIAL one ✅")

router = APIRouter()

class TrackRequest(BaseModel):
    category: str = Field(..., description="Decade/category, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"] = Field(..., description="Language used for TTS and descriptions")
    num_tracks: int = Field(..., ge=1, le=50, description="Number of tracks to generate (1–50)")

@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
def generate_track_json(request: TrackRequest):
    print("✅ A. Start generate_track_json")

    wrapped = get_top_tracks_from_xai(
        category=request.category,
        genre=request.genre,
        num_tracks=request.num_tracks,
        language=request.language
    )

    if not wrapped or "tracks" not in wrapped:
        raise HTTPException(status_code=500, detail="Failed to retrieve track list from XAI")

    track_list = wrapped["tracks"]

    enriched = get_track_descriptions_from_xai(
        track_data=wrapped,
        language=request.language,
        category=request.category,
        genre=request.genre
    )

    logging.info(f"🔍 Enriched keys: {list(enriched.keys())}")
    logging.info(f"🔢 Track count in enriched['tracks']: {len(enriched.get('tracks', []))}")

    if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
        raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

    now = datetime.now().isoformat()
    artists = []
    tracks = []
    rankings = []

    description_cache = {}

    for base in enriched["tracks"]:
        spotify_data = get_spotify_data(base['trackName'], base['artistName'])
        artist_name = base["artistName"]

        print(f"👀 Checking artist: {artist_name}")

        if artist_name not in description_cache:
            logging.info(f"🔍 Fetching description for: {artist_name}")
            desc = get_artist_description(artist_name, language=request.language)
            logging.info(f"✅ Got description: {desc}")
            if not desc:
                desc = "No biography available at this time."
            description_cache[artist_name] = desc

        artist_entry = {
            "name": artist_name,
            "spotify_artist_id": spotify_data.get("artistId") if spotify_data else None,
            "artist_artwork": None,
            "artist_description": description_cache[artist_name]
        }

        if not any(a["name"] == artist_name for a in artists):
            artists.append(artist_entry)

        track_entry = {
            "track_name": base["trackName"],
            "artist_name": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "spotify_track_id": spotify_data.get("id") if spotify_data else None,
            "duration_ms": spotify_data.get("durationMs") if spotify_data else None,
            "popularity": spotify_data.get("popularity") if spotify_data else None,
            "album_artwork": spotify_data.get("trackImage") if spotify_data else None,
            "year_released": int(base["yearReleased"]),
            "is_explicit": False,
            "created_at": now,
            "detail": base.get("detail")
        }

        tracks.append(track_entry)

        rankings.append({
            "track_name": base["trackName"],
            "artist_name": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "tracklist": "TopSpot Autogen",
            "rank": base["rank"],
            "intro": base.get("intro"),
            "intro_mp3_url": base.get("intro_mp3_url"),
            "ranking_date": now[:10]
        })

    print("👀 Artists list before writing JSON:")
    print(json.dumps(artists, indent=2))

    final_json = {
        "core_tables": {
            "genre": [{"name": request.genre}],
            "decade": [{"name": request.category}],
            "artist": artists
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
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write JSON: {e}")

    return {
        "message": "🎉 JSON created successfully",
        "file": str(filepath),
        "version": "v3-official",
        "track_count": len(track_list)
    }

