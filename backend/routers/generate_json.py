# backend/routers/generate_json.py

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import json
from backend.services.spotify_service import handle_missing_track, reassign_ranks
from backend.services.track_generator import build_track_entry



from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai,
)

from shared.filepaths import get_json_path
from backend.services.track_generator import build_final_json

from backend.utils.log_helpers import log_generate_json_summary
from backend.utils.log_helpers import log_summary_table

logger = logging.getLogger(__name__)

router = APIRouter()

class TrackRequest(BaseModel):
    decade: str = Field(..., description="Decade, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"] = Field(..., description="Language used for TTS and descriptions")
    num_tracks: int = Field(..., ge=1, le=50, description="Number of tracks to generate (1–50)")

@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
async def generate_track_json(request: TrackRequest, test_file_number: int = 0):

    try:
        logger.info("A. Start generate_track_json")

        now = datetime.now().isoformat()

        # Step 1: Get raw track list from XAI
        logger.info("B. Calling get_top_tracks_from_xai")
        wrapped = get_top_tracks_from_xai(
            decade=request.decade,
            genre=request.genre,
            num_tracks=request.num_tracks,
            language=request.language,
            test_file_number=test_file_number
        )

        if not wrapped or "tracks" not in wrapped:
            raise HTTPException(status_code=500, detail="Failed to retrieve track list from XAI")

        track_list = wrapped["tracks"]
        logger.info(f"C. Retrieved {len(track_list)} tracks from XAI")

        # Step 2: Enrich descriptions
        logger.info("D. Enriching with get_track_descriptions_from_xai")
        enriched = get_track_descriptions_from_xai(
            track_data=wrapped,
            language=request.language,
            decade=request.decade,
            genre=request.genre
        )

        if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
            raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

        # Step 3: Build final JSON structure
        final_json, track_entries, artist_entries = build_final_json(
            enriched_tracks=enriched["tracks"],
            request=request,
            now=now
        )

        print("📦 final_json keys:", final_json.keys())


        # 🧹 Filter tracks from the final JSON data
        tracks = final_json["tracks"]
        spare_tracks = final_json.get("spares", [])  # Optional: Add support for spare pool

        # 🛠 Fix or replace broken tracks
        for track in tracks[:]:  # Iterate over a copy so you can safely remove
            if not track.get("spotify_track_id"):
                handle_missing_track(track, tracks, spare_tracks)

        # 🚮 Remove any still-invalid tracks
        tracks = [t for t in tracks if t.get("spotify_track_id")]
        # 🎒 Refill to ensure 40 total tracks
        while len(tracks) < 40 and spare_tracks:
            spare = spare_tracks.pop(0)

            # 🔎 Validate required fields
            missing_keys = [key for key in ("trackName", "artistName") if key not in spare]
            if missing_keys:
                logging.warning(f"⚠️ Skipping spare track due to missing keys: {missing_keys} — {spare}")
                continue

            # 🛠 Rebuild track_entry properly
            try:
                rebuilt = build_track_entry(spare, request, spotify_data=None, now=now)
                rebuilt["rank"] = len(tracks) + 1
                tracks.append(rebuilt)
                logging.info(f"✅ Added spare track: {rebuilt['track_display_name']}")
            except Exception as e:
                logging.warning(f"❌ Failed to rebuild spare track: {e}")
                continue

        # 🔁 Update final JSON and ranks
        reassign_ranks(tracks)
        final_json["tracks"] = tracks

        # Step 4: Save to file
        filepath = get_json_path(request.decade, request.genre, request.language[:2])
        logger.info(f"F. Saving file to: {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)



        # ✅ Step 5: Log the summary
        log_generate_json_summary(
            tracks=track_entries,
            artists=artist_entries,
            now=datetime.now(),
            category=request.decade,
            genre=request.genre,
            errors=[]
        )

        # Mock stats — fill in from actual processing results
        summary_data = [
            {"decade": "1950s", "total": 40, "good": 39, "missed": 1, "duets": "None"},
            {"decade": "1960s", "total": 40, "good": 39, "missed": 1, "duets": "None"},
            {"decade": "1970s", "total": 40, "good": 35, "missed": 5, "duets": 1},
            {"decade": "1980s", "total": 40, "good": 36, "missed": 4, "duets": 2},
            {"decade": "1990s", "total": 40, "good": 39, "missed": 1, "duets": 1},
            {"decade": "2000s", "total": 40, "good": 39, "missed": 1, "duets": 3},
            {"decade": "2010s", "total": 40, "good": 39, "missed": 1, "duets": 3},
            {"decade": "2020s", "total": 40, "good": 37, "missed": 3, "duets": 3},
        ]

        log_summary_table(summary_data)

        logger.info("G. JSON creation complete")

        return {
            "message": "JSON created successfully",
            "file": str(filepath),
            "version": "v3-official",
            "track_count": len(track_list)
        }

    except Exception as e:
        logger.exception("Unexpected error in generate_track_json")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
