# backend/services/xai_response_handler.py
from backend.utils.track_helpers import set_mode_fields
import json
import logging
from backend.utils.track_helpers import normalize_track_keys

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
        # logger_step1b.debug(f"✅  [STEP_1.B] Parsed {len(tracks)} raw tracks.")
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

    logger_step1b.debug(f"🧼  [STEP_1.B] Cleaned down to {len(tracks)} valid tracks.")

    # 🕵️ Log duet/feature info if in test mode
    if is_test_mode:
        log_duet_feature_info(tracks)

    # 🎭 Analyze artist structure and assign mode fields
    for i, t in enumerate(tracks):
        if not isinstance(t, dict):
            logger_step1b.error(f"❌ Track[{i}] is not a dict: {t} (type: {type(t)})")
            raise TypeError(f"Track[{i}] must be a dict, got {type(t)}")

        t = normalize_track_keys(t, logger_step1b)

        set_mode_fields(t, logger_step1b)  # 🧠 Safe to access artist_name
        tracks[i] = t  # ✅ Save back to the list

    # ✂️ Trim to num_tracks unless in test mode
    if not is_test_mode and num_tracks > 0:
        tracks = tracks[:num_tracks]
        logger_step1b.debug(f"🔢 Trimmed to top {num_tracks} tracks (not in test mode)")

    return tracks
