# backend/tests/json_tests/xai/test_get_top_tracks_from_xai.py

import sys
import logging
import argparse
from backend.services.xai_service import get_top_tracks_from_xai
from backend.config import TEST_FILE_NUMBER, TEST_JSON_DIR
from backend.tests.test_utils import capture_logs_while_running, load_expected_data

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s]: %(message)s",
    force=True
)

# Default CLI arguments (overridden when running from terminal)
args = argparse.Namespace(category="1960s", genre="rock", num_tracks=5)

# CLI override if run directly
if __name__ == "__main__" or "pytest" not in sys.modules:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", type=str, default="1960s", help="Decade/Category, e.g. '1960s'")
    parser.add_argument("--genre", type=str, default="rock", help="Genre, e.g. 'rock'")
    parser.add_argument("--num_tracks", type=int, default=3, help="Number of tracks to fetch")
    args = parser.parse_args()

def run_test():
    logging.info(f"🔍 TESTING: XAI for {args.num_tracks} tracks in {args.genre} during {args.category}")

    # === Step 1: Run function and capture logs ===
    result, logs = capture_logs_while_running(lambda: get_top_tracks_from_xai(
        category=args.category,
        genre=args.genre,
        language="English",
        num_tracks=args.num_tracks
    ))

    assert isinstance(result, dict), "Returned value is not a dictionary"
    assert "tracks" in result, "'tracks' key missing in result"
    actual_count = len(result["tracks"])

    # === Step 2: Load expected values ===
    test_file_path = TEST_JSON_DIR / f"json_test_file_{TEST_FILE_NUMBER}.json"
    expected_count, expected_logs = load_expected_data(test_file_path)

    # === Step 3: Validate number of valid tracks ===
    assert actual_count == expected_count, f"Expected {expected_count} valid tracks, got {actual_count}"

    # === Step 4: Validate expected log entries ===
    for expected_line in expected_logs:
        assert expected_line in logs, f"Expected log not found:\n{expected_line}"

    # === Optional: Print confirmed valid tracks ===
    for track in result["tracks"]:
        logging.info(f"🎵 Rank {track.get('rank')}: {track.get('trackName')} by {track.get('artistName')}")

# === Pytest-compatible test ===
def test_get_top_tracks_from_xai_pytest():
    run_test()

# === CLI entrypoint ===
if __name__ == "__main__":
    run_test()
