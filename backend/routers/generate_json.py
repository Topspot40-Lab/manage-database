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
async def generate_track_json(request: TrackRequest, test_file_number: int = 0):
    try:
        logger.info("🟡 STEP 0: Starting generate_track_json")

        now = datetime.now().isoformat()
        # ─────────────────────────────────────────────────────────────────────────────
        # 🧠 STEP 1 — Get raw track list from XAI or test fixture
        #
        # PURPOSE:
        #   Fetches a minimal, ordered list of top tracks from XAI or a local test file.
        #   This list forms the foundation for all enrichment and metadata steps.
        #
        # BEHAVIOR:
        #   • In normal mode (test_file_number == 0):
        #       - Builds a prompt and calls XAI via chat completion
        #       - Cleans and validates JSON response (see cleanup process)
        #   • In test mode (test_file_number > 0):
        #       - Loads static file: json_test_file_{n}.json
        #       - Parses and filters using same logic as normal mode
        #
        # INPUT (from TrackRequest):
        #   - genre (str)
        #   - decade (str)
        #   - language (str)
        #   - num_tracks (int)
        #
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
        # ─────────────────────────────────────────────────────────────────────────────
        # 📥 XAI RAW INPUT FORMAT
        #
        # The XAI model returns its response inside a chat completion as Markdown-encoded JSON:
        #
        #   Example assistant message:
        #   ```json
        #   {
        #     "tracks": [
        #       { "rank": 1, "trackName": "Tennessee Waltz", "artistName": "Patti Page" },
        #       { "rank": 2, "trackName": "Cold, Cold Heart", "artistName": "Hank Williams" }
        #     ]
        #   }
        #   ```
        #
        # This string is extracted from:
        #   response["choices"][0]["message"]["content"]
        #
        # ─────────────────────────────────────────────────────────────────────────────# 🧹 CLEANUP PROCESS: Raw XAI → Structured Track List
        #
        #   1.A Markdown formatting (```json ... ```) is stripped
        #       📄 backend/services/xai_api_client.py
        #          Function: fetch_xai_tracks(prompt: str, ...)
        #          - Extracts assistant reply
        #          - Inline logic removes Markdown fencing:
        #              content = content.replace("```json", "").replace("```", "").strip()
        #
        #   1.B JSON string is parsed to Python object
        #       📄 backend/services/xai_api_client.py
        #          Function: fetch_xai_tracks()
        #          - parsed = json.loads(cleaned_string)
        #
        #   1.C Track data is validated and cleaned
        #       📄 backend/services/xai_response_handler.py
        #          Function: parse_and_filter_tracks(data, num_tracks, is_test_mode)
        #
        #          This is the critical data sanitization step that ensures the incoming
        #          track list is safe, consistent, and ready for enrichment.
        #
        #          - Accepts both input formats:
        #              {"tracks": [...]}  ← wrapped object from XAI
        #              [...]              ← raw list (used in test files or fallback cases)
        #
        #          - Normalizes track and artist names
        #              normalize_name() [utils/track_filters.py]
        #              → Converts to lowercase, trims spaces, replaces special characters
        #              → Ensures that " Beyoncé " and "beyonce" are treated the same
        #
        #          - Filters out invalid entries using is_bad_track()
        #              → Skips any item missing "trackName" or "artistName"
        #              → Also removes empty strings, non-dict items, or blank values
        #
        #          - Deduplicates the list by (trackName, artistName) combination
        #              → Uses a set of normalized (name, artist) pairs to ensure uniqueness
        #              → Prevents accidental duplicates like:
        #                   - "crazy" by "Patsy Cline"
        #                   - "Crazy" by "Patsy Cline"
        #
        #          - Caps list to `num_tracks` unless in test mode
        #              → In normal mode: only the first N valid, unique tracks are kept
        #              → In test mode: returns the full list for debugging and diagnostics
        #
        #          ✅ After this step, the returned list is guaranteed to:
        #              • Have valid fields
        #              • Be normalized and deduplicated
        #              • Contain no more than `num_tracks` items (unless testing)

        # ✅ Final cleaned format is identical in both normal and test mode:
        #   {
        #     "language": "english",
        #     "category": "1960s",
        #     "genre": "country",
        #     "generated_at": "...",
        #     "tracks": [ { "rank": 1, "trackName": "...", "artistName": "..." }, ... ]
        #   }
        #
        # NOTE:
        # - Test files must conform to this structure
        # - Downstream steps assume track names/artists are already cleaned
        # ─────────────────────────────────────────────────────────────────────────────
        # 🔄 FUNCTION CALL FLOW: Step 1 Normal vs Test Mode
        #
        # ─ Normal Mode (test_file_number == 0):
        #
        #   backend/routers/generate_json.py
        #     → generate_track_json()
        #         → backend/services/xai_service.py → get_top_tracks_from_xai()
        #             ├── xai_prompt_builder.py → build_track_prompt()
        #             ├── xai_api_client.py → fetch_xai_tracks(prompt)
        #             └── xai_response_handler.py → parse_and_filter_tracks()
        #
        # ─ Test Mode (test_file_number > 0):
        #
        #   backend/services/xai_service.py → get_top_tracks_from_xai()
        #       ├── Loads: backend/tests/json_tests/xai/json_test_file_{n}.json
        #       └── Passes it to:
        #            xai_response_handler.py → parse_and_filter_tracks(data, ...)
        #
        # 🔗 The result of STEP 1 is the canonical input for:
        #     STEP 2 (XAI descriptions), STEP 3 (Spotify enrichment), and beyond.
        # ─────────────────────────────────────────────────────────────────────────────

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
