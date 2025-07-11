# backend/routers/generate_json.py

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
import json
from backend.services.spotify.missing_log import (
    handle_missing_track,
    reassign_ranks,
)

from backend.utils.logger_factory import get_step_logger
from backend.utils.track_builder import build_track_entry, build_final_json
from backend.services.track_generator import enrich_tracks_with_spotify
from backend.routers.steps.step_01_get_tracks import run as step01_get_tracks
from backend.services.xai_descriptions import get_track_descriptions_from_xai

from shared.filepaths import get_json_path
from pydantic import BaseModel

from backend.utils.log_helpers import log_generate_json_summary

logger = logging.getLogger(__name__)
logger_step4e = get_step_logger("STEP_4.E")

router = APIRouter()



class TrackRequest(BaseModel):
    decade: str = "1950s"
    genre: str = "country"
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

        logger.debug("🟡 STEP 0: Starting generate_track_json")
        now_dt = datetime.now()
        now = now_dt.isoformat()

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

        logger.info("🛑 Step 1 ----- Complete")
        # ───────────────── STEP 2 ─────────────────
        logger.debug("✍️ STEP 2: Enriching tracks with XAI descriptions")
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
        logger.info("🛑 Step 2 ----- Complete")
        # ───────────────── STEP 3 ─────────────────
        logger.debug("✍️ STEP 3: Enriching tracks with Spotify API")
        enriched["tracks"] = enrich_tracks_with_spotify(
            enriched["tracks"], is_test_mode=(test_file_number > 0)
        )
        logger.info("🛑 Step 3 ----- Complete")

        if max_step == 3:
            logger.info("        🛑 Stopping after STEP 3 as requested")
            return {"message": "Stopped after STEP 3"}

        # ───────────────── STEP 4 ─────────────────
        logger.debug("🧱 STEP 4: Building full JSON structure from enriched data")
        is_test_mode = test_file_number > 0

        final_json, track_entries, artist_entries = build_final_json(
            enriched_tracks=enriched["tracks"],
            request=request,
            now=now,
            is_test_mode=is_test_mode
        )

        # ✅ STEP 4 Summary Output
        logger.debug("📋 STEP 4 SUMMARY: Track Listing")
        tracks = final_json["track_tables"]["track"]
        for t in tracks:
            rank = t.get("rank")
            name = t.get("trackName") or t.get("track_name")
            artist = t.get("artistName") or t.get("artist_name")
            track_id = t.get("spotify_track_id")
            if track_id:
                logger.debug(f"   #{rank:02d} — {name} by {artist} 🎧 {track_id}")
            else:
                logger.warning(f"   #{rank:02d} — {name} by {artist} ❌ MISSING Spotify ID")


        logger_step4e.debug("🧾 STEP 4.E: Final JSON preview (pretty-printed)")
        logger_step4e.debug(json.dumps(final_json, indent=2, ensure_ascii=False))

        logger.info("🛑 Step 4 ----- Complete")

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
        logger.debug("🧹 STEP 5: Handling tracks with missing Spotify IDs")
        tracks = final_json["track_tables"]["track"]
        spare_tracks = final_json.get("spares", [])

        for track in tracks[:]:
            if not track.get("spotify_track_id"):
                handle_missing_track(track, tracks)

        logger.info("🛑 Step 5 ----- Complete")

        # 🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement
        logger.debug("🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement")
        tracks = [t for t in tracks if t.get("spotify_track_id")]

        logger.info("🛑 Step 6 ----- Complete")

        # ➕ STEP 7: Filling in with spare tracks to ensure 40 total
        logger.debug("➕ STEP 7: Filling in with spare tracks to ensure 40 total")
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

            logger.info("🛑 Step 7 ----- Complete")

        # 🔢 STEP 8: Reassigning ranks and finalizing track table
        logger.debug("🔢 STEP 8: Reassigning ranks and finalizing track table")
        reassign_ranks(tracks)
        final_json["track_tables"]["track"] = tracks

        logger.info("🛑 Step 8 ----- Complete")

        # 👨‍🎤 STEP 9: Rebuilding artist table from track data
        # logger.debug("👨‍🎤 STEP 9: Rebuilding artist table from track data")
        # artist_lookup = {}
        # for t in tracks:
        #     aid = t.get("spotify_artist_id")
        #     if not aid:
        #         continue
        #     if aid not in artist_lookup:
        #         artist_lookup[aid] = {
        #             "artist_name": t.get("artist_name"),
        #             "spotify_artist_id": aid,
        #             "artist_artwork": t.get("artist_artwork"),
        #             "artist_description": None,
        #             "artist_mp3_url": None,
        #             "not_on_spotify": t.get("not_on_spotify", False)
        #         }
        # final_json["core_tables"]["artist"] = list(artist_lookup.values())
        #
        logger.info("🛑 Step 9 ----- Complete")

        # 💾 STEP 10: Saving final JSON to file
        filepath = get_json_path(request.decade, request.genre, request.language[:2])
        logger.debug(f"💾 STEP 10: Saving final JSON to file: {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)

        logger.info("🛑 Step 10 ----- Complete")

        # 📊 STEP 11: Logging summary report
        logger.debug("📊 STEP 11: Logging summary report")
        log_generate_json_summary(
            tracks=track_entries,
            artists=artist_entries,

            now=datetime.now(),
            category=request.decade,
            genre=request.genre,
            errors=[]
        )

        # Save the full final_json to the file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ JSON saved to {filepath}")

        logger.info("🛑 Step 11 ----- JSON Creation Complete")

        return {
            "message": "JSON created successfully",
            "file": str(filepath),
            "version": "v3-official",
            "track_count": len(tracks)
        }


    except Exception as e:
        logger.exception("❌ Unexpected error in generate_track_json")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
