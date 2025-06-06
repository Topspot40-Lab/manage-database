# backend/tests/json_tests/xai/test_get_top_tracks_from_xai.py

"""
📄 Test Script: test_get_top_tracks_from_xai.py

This script tests the `get_top_tracks_from_xai()` function using structured JSON test files
and log verification. It can be executed in two ways:

1. ✅ As a standalone Python script (e.g., with CLI args)
2. ✅ As a `pytest`-compatible test suite

The test validates:
- That a dictionary with a 'tracks' key is returned
- That the number of valid tracks matches expected test data
- That expected log lines were emitted during execution

Test input and expectations are controlled by:
- --category        → Decade (e.g., "1960s")
- --genre           → Genre (e.g., "rock")
- --num_tracks      → Target number of tracks
- --test_file_number → Index of test file (e.g., 1 = json_test_file_1.json)

🎯 Example CLI Usage:
python test_get_top_tracks_from_xai.py --category 1960s --genre rock --num_tracks 5 --test_file_number 1

python backend/tests/json_tests/xai/test_get_top_tracks_from_xai.py \
  --category 1960s \
  --genre rock \
  --num_tracks 5 \
  --test_file_number 1
"""

import sys
import logging
import argparse
from pathlib import Path

from backend.services.xai_service import get_top_tracks_from_xai
from backend.tests.test_utils import capture_logs_while_running, load_expected_data
from backend.config import TEST_JSON_DIR  # Location of test JSON files

# Dynamically add the project root to sys.path
project_root = Path(__file__).resolve().parents[4]  # adjust as needed
sys.path.insert(0, str(project_root))


# -----------------------------------------------------------------------------
# 📋 Configure Logging Format and Level
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s]: %(message)s",
    force=True  # Override any previous logging config (important in test runners)
)

# -----------------------------------------------------------------------------
# 💡 Default CLI arguments (used when running under pytest)
# These will be overridden when called via the command line
# -----------------------------------------------------------------------------
args = argparse.Namespace(
    category="1960s",
    genre="rock",
    num_tracks=5,
    test_file_number=1
)

# -----------------------------------------------------------------------------
# 🧪 CLI Argument Parsing (when script is executed directly)
# -----------------------------------------------------------------------------
if __name__ == "__main__" or "pytest" not in sys.modules:
    parser = argparse.ArgumentParser(description="Run XAI track test against a specific test JSON file")
    parser.add_argument("--category", type=str, default="1960s", help="Decade or category (e.g., '1960s')")
    parser.add_argument("--genre", type=str, default="rock", help="Music genre (e.g., 'rock')")
    parser.add_argument("--num_tracks", type=int, default=5, help="Number of top tracks to request")
    parser.add_argument("--test_file_number", type=int, default=1, help="Index of test file (e.g., 1 = json_test_file_1.json)")
    args = parser.parse_args()

# -----------------------------------------------------------------------------
# 🧪 Core Test Logic (shared by both CLI and pytest)
# -----------------------------------------------------------------------------
def run_test():
    """
    Run a functional test of `get_top_tracks_from_xai()` against expected test data and logs.
    Verifies:
      - Correct return structure
      - Correct number of tracks
      - Log output contains expected messages
    """
    logging.info(f"🔍 TESTING: {args.num_tracks} tracks in {args.genre} ({args.category}) [Test File #{args.test_file_number}]")

    # === Step 1: Run the target function and capture its log output
    result, logs = capture_logs_while_running(lambda: get_top_tracks_from_xai(
        category=args.category,
        genre=args.genre,
        language="English",
        num_tracks=args.num_tracks
    ))

    # === Step 2: Validate structure of the returned result
    assert isinstance(result, dict), "❌ Returned value is not a dictionary"
    assert "tracks" in result, "❌ Missing 'tracks' key in returned result"
    actual_count = len(result["tracks"])

    # === Step 3: Load expected results and logs from test JSON file
    test_file_path = TEST_JSON_DIR / f"json_test_file_{args.test_file_number}.json"
    expected_count, expected_logs = load_expected_data(test_file_path)

    # === Step 4: Validate number of valid tracks returned
    assert actual_count == expected_count, (
        f"❌ Expected {expected_count} valid tracks, but got {actual_count}"
    )

    # === Step 5: Validate expected log messages were emitted
    for expected_line in expected_logs:
        assert expected_line in logs, f"❌ Expected log line not found:\n{expected_line}"

    # === Optional: Log each track for confirmation
    for track in result["tracks"]:
        logging.info(f"🎵 Rank {track.get('rank')}: {track.get('trackName')} by {track.get('artistName')}")

# -----------------------------------------------------------------------------
# ✅ Pytest-Compatible Wrapper Function
# -----------------------------------------------------------------------------
def test_get_top_tracks_from_xai_pytest():
    """
    Allows this test to be discovered and run by pytest.
    Uses default CLI arguments defined above unless overridden.
    """
    run_test()

# -----------------------------------------------------------------------------
# 🏁 CLI Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    run_test()
