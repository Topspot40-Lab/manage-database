# backend/services/xai_response_handler.py

import json
import logging

from backend.utils.track_filters import is_bad_track
from backend.logging.track_logging import (
    log_raw_tracks,
    log_filtered_out,
    log_duet_feature_info
)

# Use STEP_1.B logger consistently
logger_step1b = logging.getLogger("STEP_1.B")

"""
STEP 1.B — JSON Parsing and Filtering

Parses raw track data from XAI (as a JSON string), filters out unusable or invalid entries,
and returns a cleaned list of track dictionaries.

This function:
- Parses the JSON string into a Python list
- Logs the raw track data for debugging (with rank/artist info)
- Removes duplicate, malformed, or placeholder tracks using `is_bad_track`
- Logs how many tracks were filtered out
- Logs duet/feature artist notes (if test mode is enabled)
- (Optional) Trims to `num_tracks` if buffer was added

Args:
    json_input (str): Raw JSON string returned by XAI
    num_tracks (int): Desired number of final tracks
    is_test_mode (bool): Enables extra debug logs (e.g., duet detection)

Returns:
    list[dict]: A cleaned, validated list of track dictionaries
"""


def parse_and_filter_tracks(json_input, num_tracks, is_test_mode=False):
    """
    Parses the raw track data (as JSON string), filters out invalid entries,
    and trims to `num_tracks` unless in test mode.
    """
    logger_step1b.debug("🧾 [STEP_1.B] Starting JSON parsing and filtering...")

    try:
        tracks = json.loads(json_input)
        logger_step1b.info(f"✅  [STEP_1.B] Parsed {len(tracks)} raw tracks.")
    except json.JSONDecodeError as e:
        logger_step1b.error(f"❌ JSON parsing failed: {e}")
        raise

    original_count = len(tracks)

    # 🪵 Log raw input tracks with rank
    log_raw_tracks(tracks)

    # 🧹 Filter bad tracks
    tracks = [t for t in tracks if not is_bad_track(t)]
    filtered_out = original_count - len(tracks)
    log_filtered_out(filtered_out)

    logger_step1b.info(f"🧼  [STEP_1.B] Cleaned down to {len(tracks)} valid tracks.")

    # 🕵️ Log duet/feature info if in test mode
    if is_test_mode:
        log_duet_feature_info(tracks)

    # 🛑 Optional: Keep trim logic commented for now
    # if not is_test_mode and len(tracks) > num_tracks:
    #     logger_step1b.info(f"[TRIM] Reducing track count from {len(tracks)} to {num_tracks}")
    #     tracks = tracks[:num_tracks]

    return tracks
