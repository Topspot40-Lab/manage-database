# backend/routers/generate_json.py

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
import json
from backend.services.spotify_service import handle_missing_track, reassign_ranks
from backend.utils.track_builder import build_track_entry, build_final_json
from backend.services.track_generator import enrich_tracks_with_spotify
from backend.routers.steps.step_01_get_tracks import run as step01_get_tracks

from backend.services.xai_service import (
    get_track_descriptions_from_xai,
)
from shared.filepaths import get_json_path
from pydantic import BaseModel

from backend.utils.log_helpers import log_generate_json_summary

logger = logging.getLogger(__name__)

router = APIRouter()



class TrackRequest(BaseModel):
    decade: str = "country"
    genre: str = "1950s"
    language: str  = "english"
    num_tracks: int = 1


# ─────────────────────────────────────────────────────────────────────────────
# 🧠 FUNCTION FLOW OVERVIEW: generate_track_json()
#
# This endpoint generates a complete TopSpot-style track listing by calling XAI,
# enriching with Spotify metadata, and assembling a structured JSON file.
#
# ─ STEP 1: Get initial track list from XAI or test file
#     backend/services/xai_service.py → get_top_tracks_from_xai()
#         ├── xai_prompt_builder.build_track_prompt()
#         ├── xai_service.fetch_xai_tracks()
#         └── xai_response_handler.parse_and_filter_tracks()
#
# ─ STEP 2: Add descriptions (intro + detail) using XAI
#     backend/services/xai_service.py → get_track_descriptions_from_xai()
#         ├── xai_prompt_builder.build_description_prompt()
#         ├── xai_service.fetch_xai_descriptions()
#         └── xai_response_handler.attach_descriptions_to_tracks()
#
# ─ STEP 3: Enrich with Spotify metadata (skipped if test mode)
#     backend/services/track_generator.py → enrich_tracks_with_spotify()
#         ├── spotify_service.get_spotify_data()
#         └── track_builder.build_track_entry()
#
# ─ STEP 4: Build structured JSON (core_tables, track_tables, ranking_tables)
#     backend/utils/track_builder.py → build_final_json()
#         └── internally calls build_track_entry() per track
#
# ─ STEP 5: Replace any missing Spotify tracks
#     backend/services/spotify_service.py → handle_missing_track()
#
# ─ STEP 6: Remove tracks still missing Spotify data
#     Inline filtering with list comprehension:
#         [t for t in tracks if t.get("spotify_track_id")]
#
# ─ STEP 7: Add spare tracks if final count < 40
#     backend/utils/track_builder.py → build_track_entry()
#         (called again to rebuild spares and assign rank)
#
# ─ STEP 8: Reassign ranks after cleanup/replacement
#     backend/services/spotify_service.py → reassign_ranks()
#
# ─ STEP 9: Rebuild artist table from enriched tracks
#     Inline logic inside generate_track_json() using:
#         track["spotify_artist_id"] → artist_lookup[aid]
#
# ─ STEP 10: Save final JSON to disk
#     shared/filepaths.py → get_json_path()
#     → standard open() and json.dump() to file
#
# ─ STEP 11: Print summary to terminal
#     backend/utils/log_helpers.py → log_generate_json_summary()
# OUTPUT (wrapped dict):
#   {
#     "language": "english",
#     "category": "1960s",
#     "genre": "rock",
#     "generated_at": "ISO timestamp",
#     "tracks": [
#         { "rank": 1, "trackName": "Tennessee Waltz", "artistName": "Patti Page" },
#         ...
#     ]
#   }
#
# STORED IN:
#   The variable name for this structure is `wrapped`, returned by get_top_tracks_from_xai().
#   The cleaned track list used in later steps is accessed via:
#       track_list = wrapped["tracks"]
#
#   ✅ This is the canonical track list for enrichment, Spotify lookup, and final output.
#
# ✅ Final return includes:
#     {
#       "message": "JSON created successfully",
#       "file": <saved path>,
#       "version": "v3-official",
#       "track_count": <original XAI count>
#     }
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
async def generate_track_json(
    request: TrackRequest,
    test_file_number: int = 0,
    max_step: int = 11
):
    try:  # ────────────────────────────────────────────────────────
        if not 1 <= max_step <= 11:
            raise HTTPException(status_code=400,
                                detail="max_step must be between 1 and 11")

        logger.info("🟡 STEP 0: Starting generate_track_json")
        now = datetime.now().isoformat()

        # ───────────────── STEP 1 ─────────────────
        wrapped = step01_get_tracks(request, test_file_number=test_file_number)
        track_list = wrapped["tracks"]

        if max_step == 1:
            logger.info("🛑 Stopping after STEP 1 as requested")
            return {
                "message": "Stopped after STEP 1",
                "track_count": len(track_list),
                "tracks": track_list
            }
        # ───────────────── STEP 2 ─────────────────
        logger.info("✍️ STEP 2: Enriching tracks with XAI descriptions")
        enriched = get_track_descriptions_from_xai(
            track_data=wrapped,
            language=request.language,
            decade=request.decade,
            genre=request.genre
        )
        if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
            raise HTTPException(status_code=500,
                                detail="Mismatch or failure in track descriptions")

        if max_step == 2:
            logger.info("🛑 Stopping after STEP 2 as requested")
            return {
                "message": "Stopped after STEP 2",
                "track_count": len(enriched['tracks']),
                "tracks": enriched["tracks"]
            }

        # ───────────────── STEP 3 ─────────────────
        if test_file_number == 0:
            logger.info("🎧 STEP 3: Enriching tracks with Spotify metadata")
            enriched["tracks"] = enrich_tracks_with_spotify(enriched["tracks"])
        else:
            logger.info("🎧 STEP 3: Skipping Spotify enrichment (test mode)")

        if max_step == 3:
            logger.info("🛑 Stopping after STEP 3 as requested")
            return {"message": "Stopped after STEP 3"}

        # ───────────────── STEP 4 ─────────────────
        is_test_mode = test_file_number > 0
        logger.info("🧱 STEP 4: Building full JSON structure from enriched data")
        final_json, track_entries, artist_entries = build_final_json(
            enriched_tracks=enriched["tracks"],
            request=request,
            now=now,
            is_test_mode=is_test_mode
        )

        if max_step == 4:
            logger.info("🛑 Stopping after STEP 4 as requested")
            return {"message": "Stopped after STEP 4", "preview": final_json}

        # ───────────── STEP 5 - STEP 11 (unchanged) ─────────────
        # Make sure all the following code stays at **this** indent.
        # … STEP 5 replacement logic …
        # … STEP 6 remove invalid …
        # … STEP 7 add spares …
        # … STEP 8 reassign ranks …
        # … STEP 9 rebuild artist table …
        # … STEP 10 save JSON …
        # … STEP 11 summary …

        # 🧹 STEP 5: Handling tracks with missing Spotify IDs
        logger.info("🧹 STEP 5: Handling tracks with missing Spotify IDs")
        tracks = final_json["track_tables"]["track"]
        spare_tracks = final_json.get("spares", [])

        for track in tracks[:]:
            if not track.get("spotify_track_id"):
                handle_missing_track(track, tracks, spare_tracks)

        # 🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement
        logger.info("🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement")
        tracks = [t for t in tracks if t.get("spotify_track_id")]

        # ➕ STEP 7: Filling in with spare tracks to ensure 40 total
        logger.info("➕ STEP 7: Filling in with spare tracks to ensure 40 total")
        while len(tracks) < 40 and spare_tracks:
            spare = spare_tracks.pop(0)
            missing_keys = [key for key in ("trackName", "artistName") if key not in spare]
            if missing_keys:
                logger.warning(f"⚠️ Skipping spare track due to missing keys: {missing_keys} — {spare}")
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
                logger.info(f"✅ Spare track added: {rebuilt['artist_display_name']}")
            except Exception as e:
                logger.warning(f"❌ Failed to rebuild spare track: {e}")
                continue

        # 🔢 STEP 8: Reassigning ranks and finalizing track table
        logger.info("🔢 STEP 8: Reassigning ranks and finalizing track table")
        reassign_ranks(tracks)
        final_json["track_tables"]["track"] = tracks

        # 👨‍🎤 STEP 9: Rebuilding artist table from track data
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

        # 💾 STEP 10: Saving final JSON to file
        filepath = get_json_path(request.decade, request.genre, request.language[:2])
        logger.info(f"💾 STEP 10: Saving final JSON to file: {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)

        # 📊 STEP 11: Logging summary report
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


    except Exception as e:
        logger.exception("❌ Unexpected error in generate_track_json")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
