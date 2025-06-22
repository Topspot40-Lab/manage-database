import json
import logging
from backend.utils.track_filters import is_bad_track
def parse_and_filter_tracks(json_input, num_tracks, is_test_mode=False):
    """
    Parses the raw track data (as JSON string), filters out invalid entries,
    and trims to `num_tracks` unless in test mode.
    """
    tracks = json.loads(json_input)
    original_count = len(tracks)

    # DEBUG: Log each raw track before filtering
    for i, t in enumerate(tracks, 1):
        logging.debug(f"[TRACK RAW {i}] {t}")

    # Apply main filtering logic
    tracks = [t for t in tracks if not is_bad_track(t)]
    filtered_out = original_count - len(tracks)

    if filtered_out:
        logging.info(f"[CLEANUP] Filtered {filtered_out} hallucinated or invalid track(s).")

    # Optional logging for test mode — detect duet/feature pairings
    if is_test_mode:
        for t in tracks:
            artist_name_raw = t.get("artistName", "")
            artist_name_lower = artist_name_raw.lower()

            if " with " in artist_name_lower:
                logging.info(f"[DUET DETECTED] {artist_name_raw.title()}")
            elif " feat." in artist_name_lower or " ft. " in artist_name_lower:
                logging.info(f"[FEATURED DETECTED] {artist_name_raw.title()}")

    # Trim to requested count if not in test mode
    # if not is_test_mode and len(tracks) > num_tracks:
    #     logging.info(f"[TRIM] Reducing track count from {len(tracks)} to {num_tracks}")
    #     tracks = tracks[:num_tracks]

    return tracks

