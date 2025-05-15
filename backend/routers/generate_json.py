# backend/routers/generate_json.py
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai,
)
from backend.services.spotify_service import get_spotify_data
from utils.json_helpers import save_json

router = APIRouter(tags=["json-generate"])

# ──────────────────────────────────────────────────────────────────────────
# Pydantic request model
# ──────────────────────────────────────────────────────────────────────────
class TrackRequest(BaseModel):
    category: str = Field(..., description="Decade/category, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"]
    num_tracks: int = Field(..., ge=1, le=50)

# ──────────────────────────────────────────────────────────────────────────
# POST /generate-json
# ──────────────────────────────────────────────────────────────────────────
@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
def generate_track_json(request: TrackRequest):
    # 1️⃣  Ask XAI for a base list of tracks
    wrapped = get_top_tracks_from_xai(
        category=request.category,
        genre=request.genre,
        num_tracks=request.num_tracks,
        language=request.language,
    )
    if not wrapped or "tracks" not in wrapped:
        raise HTTPException(500, "Failed to retrieve track list from XAI")

    # 2️⃣  Ask XAI for Casey-Kasem-style descriptions
    enriched = get_track_descriptions_from_xai(
        track_data=wrapped,
        language=request.language,
        category=request.category,
        genre=request.genre,
    )
    if (
        not enriched
        or "tracks" not in enriched
        or len(enriched["tracks"]) != len(wrapped["tracks"])
    ):
        raise HTTPException(500, "Mismatch or failure in track descriptions")

    # 3️⃣  Build artists, tracks, rankings + enrich with Spotify
    now = datetime.now(timezone.utc).isoformat()
    artists, tracks, rankings = [], [], []

    for base in enriched["tracks"]:
        spotify = get_spotify_data(base["trackName"], base["artistName"])

        # ----- artist table -----
        artist_rec = {
            "name": base["artistName"],
            "spotify_artist_id": spotify.get("artistId") if spotify else None,
            "artist_artwork": None,
            "artist_description": "",
        }
        if artist_rec not in artists:
            artists.append(artist_rec)

        # ----- track table -----
        tracks.append(
            {
                "name": base["trackName"],
                "artistName": base["artistName"],
                "genre": request.genre,
                "decade": request.category,
                "spotify_track_id": spotify.get("id") if spotify else None,
                "duration_ms": spotify.get("durationMs") if spotify else None,
                "popularity": spotify.get("popularity") if spotify else None,
                "album_artwork": spotify.get("trackImage") if spotify else None,
                "year_released": int(base["yearReleased"]),
                "is_explicit": False,
                "created_at": now,
            }
        )

        # ----- ranking table -----
        rankings.append(
            {
                "trackName": base["trackName"],
                "artistName": base["artistName"],
                "genre": request.genre,
                "decade": request.category,
                "tracklist": "TopSpot Autogen",
                "rank": base["rank"],
                "intro": base.get("intro"),
                "detail": base.get("detail"),
                "description_language": request.language,
                "ranking_date": now[:10],
            }
        )

    # 4️⃣  Assemble the *final_json* payload
    final_json = {
        "core_tables": {
            "genre": [{"name": request.genre}],
            "decade": [{"name": request.category}],
            "artist": artists,
            "language": [
                {"code": request.language[:2].lower(), "name": request.language}
            ],
            "specialty": [],
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
                    "created_at": now,
                }
            ],
        },
        "ranking_tables": {"trackranking": rankings},
    }

    # 5️⃣  Persist it
    filename = f"{request.category}_{request.genre}_{request.language[:2].lower()}.json"
    try:
        save_json(final_json, request.category, filename)
    except Exception as e:
        raise HTTPException(500, f"Failed to write JSON: {e}")

    return {
        "message": "🎉 JSON created successfully",
        "file": filename,
        "track_count": len(tracks),
    }
