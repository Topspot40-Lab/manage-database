# backend/services/xai_response_handler.py

import json
from backend.utils.track_filters import is_bad_track
from backend.logging.track_logging import (
    log_raw_tracks,
    log_filtered_out,
    log_duet_feature_info
)

def parse_and_filter_tracks(json_input, num_tracks, is_test_mode=False):
    """
    Parses the raw track data (as JSON string), filters out invalid entries,
    and trims to `num_tracks` unless in test mode.
    """
    tracks = json.loads(json_input)
    original_count = len(tracks)

    # 🪵 Log raw input tracks with rank
    log_raw_tracks(tracks)

    # 🧹 Filter bad tracks
    tracks = [t for t in tracks if not is_bad_track(t)]
    filtered_out = original_count - len(tracks)
    log_filtered_out(filtered_out)

    # 🕵️ Log duet/feature info if in test mode
    if is_test_mode:
        log_duet_feature_info(tracks)

    # 🛑 Optional: Keep trim logic commented for now
    # if not is_test_mode and len(tracks) > num_tracks:
    #     logging.info(f"[TRIM] Reducing track count from {len(tracks)} to {num_tracks}")
    #     tracks = tracks[:num_tracks]

    return tracks
