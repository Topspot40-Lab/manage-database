# backend/routers/steps/step_01_get_tracks.py
import logging
from fastapi import HTTPException

from backend.services.xai_service import get_top_tracks_from_xai
from pydantic import BaseModel

logger = logging.getLogger("step_01")       # 🔍 control in config via STEP_1 or step_01

class TrackRequest(BaseModel):
    genre: str
    decade: str
    language: str
    num_tracks: int


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


def run(request: TrackRequest, *, test_file_number: int = 0) -> dict:
    """STEP 1 – fetch & clean the raw XAI track list (or test file)."""
    logger.info("🧠 STEP 1: Requesting raw track list from XAI")

    wrapped = get_top_tracks_from_xai(
        decade=request.decade,
        genre=request.genre,
        num_tracks=request.num_tracks,
        language=request.language,
        test_file_number=test_file_number
    )
    if not wrapped or "tracks" not in wrapped:
        raise HTTPException(status_code=500,
                            detail="Failed to retrieve track list from XAI")

    logger.debug("✅ STEP 1 returned %d tracks", len(wrapped["tracks"]))
    return wrapped        # canonical input for later steps
