# backend/routers/generate_json.py

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
import json
from backend.services.spotify_service import handle_missing_track, reassign_ranks
from backend.utils.track_builder import build_track_entry, build_final_json
from backend.services.track_generator import enrich_tracks_with_spotify


from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai,
)
from shared.filepaths import get_json_path
from pydantic import BaseModel

from backend.utils.log_helpers import log_generate_json_summary

logger = logging.getLogger(__name__)

router = APIRouter()



class TrackRequest(BaseModel):
    genre: str
    decade: str
    language: str
    num_tracks: int

@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
async def generate_track_json(request: TrackRequest, test_file_number: int = 0):
    try:
        logger.info("🟡 STEP 0: Starting generate_track_json")

        now = datetime.now().isoformat()

        # 🧠 STEP 1: Get initial track list from XAI
        logger.info("🧠 STEP 1: Requesting raw track list from XAI")
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

        # ✍️ STEP 2: Add descriptions (intro and detail) to tracks
        logger.info("✍️ STEP 2: Enriching tracks with XAI descriptions")
        enriched = get_track_descriptions_from_xai(
            track_data=wrapped,
            language=request.language,
            decade=request.decade,
            genre=request.genre
        )
        if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
            raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

        # 🎧 STEP 3: Add Spotify metadata if not in test mode
        if test_file_number == 0:
            logger.info("🎧 STEP 3: Enriching tracks with Spotify metadata")
            enriched["tracks"] = enrich_tracks_with_spotify(enriched["tracks"])
        else:
            logger.info("🎧 STEP 3: Skipping Spotify enrichment (test mode)")

        # 🧱 STEP 4: Build full JSON structure (core_tables, track_tables, ranking_tables)
        is_test_mode = test_file_number > 0
        logger.info("🧱 STEP 4: Building full JSON structure from enriched data")
        final_json, track_entries, artist_entries = build_final_json(
            enriched_tracks=enriched["tracks"],
            request=request,
            now=now,
            is_test_mode=is_test_mode
        )

        # 🧹 STEP 5: Clean up bad/missing tracks
        logger.info("🧹 STEP 5: Handling tracks with missing Spotify IDs")
        tracks = final_json["track_tables"]["track"]
        spare_tracks = final_json.get("spares", [])

        for track in tracks[:]:
            if not track.get("spotify_track_id"):
                handle_missing_track(track, tracks, spare_tracks)

        # 🗑 STEP 6: Remove any still-invalid tracks
        logger.info("🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement")
        tracks = [t for t in tracks if t.get("spotify_track_id")]

        # ➕ STEP 7: Fill in with spare tracks if fewer than 40
        logger.info("➕ STEP 7: Filling in with spare tracks to ensure 40 total")
        while len(tracks) < 40 and spare_tracks:
            spare = spare_tracks.pop(0)
            missing_keys = [key for key in ("trackName", "artistName") if key not in spare]
            if missing_keys:
                logging.warning(f"⚠️ Skipping spare track due to missing keys: {missing_keys} — {spare}")
                continue
            try:
                rebuilt = build_track_entry(
                    spare,
                    request,
                    spotify_data=None,
                    now=now,
                    is_test_mode=is_test_mode
                )
                rebuilt["rank"] = len(tracks) + 1
                tracks.append(rebuilt)
                logging.info(f"✅ Spare track added: {rebuilt['artist_display_name']}")
            except Exception as e:
                logging.warning(f"❌ Failed to rebuild spare track: {e}")
                continue

        # 🔢 STEP 8: Update ranks and finalize track list
        logger.info("🔢 STEP 8: Reassigning ranks and finalizing track table")
        reassign_ranks(tracks)
        final_json["track_tables"]["track"] = tracks

        # 👨‍🎤 STEP 9: Rebuild artist table (deduplicated by artist_id)
        logger.info("👨‍🎤 STEP 9: Rebuilding artist table from track data")
        artist_lookup = {}
        for t in tracks:
            aid = t.get("spotify_artist_id")
            if not aid:
                continue
            if aid not in artist_lookup:
                artist_lookup[aid] = {
                    "artist_name": t.get("artist_name"),
                    "spotify_artist_id": aid,
                    "artist_artwork": t.get("artist_artwork"),
                    "artist_description": None,
                    "artist_mp3_url": None,
                    "not_on_spotify": t.get("not_on_spotify", False)
                }
        final_json["core_tables"]["artist"] = list(artist_lookup.values())

        # 💾 STEP 10: Save final JSON to disk
        filepath = get_json_path(request.decade, request.genre, request.language[:2])
        logger.info(f"💾 STEP 10: Saving final JSON to file: {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)

        # 📊 STEP 11: Print summary to terminal
        logger.info("📊 STEP 11: Logging summary report")
        log_generate_json_summary(
            tracks=track_entries,
            artists=artist_entries,
            now=datetime.now(),
            category=request.decade,
            genre=request.genre,
            errors=[]
        )

        logger.info("✅ JSON creation complete")

        return {
            "message": "JSON created successfully",
            "file": str(filepath),
            "version": "v3-official",
            "track_count": len(track_list)
        }

    except Exception as e:
        logger.exception("❌ Unexpected error in generate_track_json")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
