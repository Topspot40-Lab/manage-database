# backend/services/xai_response_handler.py

import json
import logging
from utils.track_filters import is_bad_track

def parse_and_filter_tracks(content, num_tracks):
    tracks = json.loads(content)
    original_count = len(tracks)
    tracks = [t for t in tracks if not is_bad_track(t)]
    filtered_out = original_count - len(tracks)

    if filtered_out:
        logging.info(f"🧹 Filtered {filtered_out} hallucinated or invalid track(s).")

    if len(tracks) > num_tracks:
        logging.info(f"✂️ Trimming {len(tracks)} → {num_tracks}")
        tracks = tracks[:num_tracks]

    return tracks
