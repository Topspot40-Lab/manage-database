# backend/routers/generate_json.py

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import json

from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai,
)

from shared.filepaths import get_json_path
from backend.services.track_generator import build_final_json  # ✅ fixed import

logging.info("🪩 generate_json.py is now the OFFICIAL one ✅")

router = APIRouter()

class TrackRequest(BaseModel):
    decade: str = Field(..., description="Decade, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"] = Field(..., description="Language used for TTS and descriptions")
    num_tracks: int = Field(..., ge=1, le=50, description="Number of tracks to generate (1–50)")

@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
def generate_track_json(request: TrackRequest):
    try:
        logging.info("✅ A. Start generate_track_json")

        now = datetime.now().isoformat()

        # Step 1: Get raw track list from XAI
        logging.info("🔍 B. Calling get_top_tracks_from_xai")
        wrapped = get_top_tracks_from_xai(
            decade=request.decade,
            genre=request.genre,
            num_tracks=request.num_tracks,
            language=request.language
        )

        if not wrapped or "tracks" not in wrapped:
            raise HTTPException(status_code=500, detail="Failed to retrieve track list from XAI")

        track_list = wrapped["tracks"]
        logging.info(f"📦 C. Retrieved {len(track_list)} tracks from XAI")

        # Step 2: Enrich descriptions
        logging.info("🧠 D. Enriching with get_track_descriptions_from_xai")
        enriched = get_track_descriptions_from_xai(
            track_data=wrapped,
            language=request.language,
            decade=request.decade,
            genre=request.genre
        )

        if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
            raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

        # Step 3: Build final JSON structure
        logging.info("🗱 E. Building final JSON with build_final_json")
        final_json = build_final_json(
            enriched_tracks=enriched["tracks"],
            request=request,
            now=now
        )

        # Step 4: Save to file
        filepath = get_json_path(request.decade, request.genre, request.language[:2])
        logging.info(f"📂 F. Saving file to: {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)

        logging.info("✅ G. JSON creation complete!")

        return {
            "message": "🎉 JSON created successfully",
            "file": str(filepath),
            "version": "v3-official",
            "track_count": len(track_list)
        }

    except Exception as e:
        logging.exception("🔥 Unexpected error in generate_track_json")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
