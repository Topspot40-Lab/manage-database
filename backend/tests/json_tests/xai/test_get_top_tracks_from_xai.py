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
- --category         → Decade (e.g., "1960s")
- --genre            → Genre (e.g., "rock")
- --num_tracks       → Target number of tracks
- --test_file_number → Index of test file (e.g., 1 = json_test_file_1.json)

🎯 Example CLI Usage:
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

# 🔍 Dynamically find the project root and inject it into sys.path
full_path = Path(__file__).resolve()
print("🧭 Full path to test file:", full_path)
for i, parent in enumerate(full_path.parents[:6]):
    print(f"parents[{i}] = {parent}")

# 🔧 Correct project root (should contain the 'backend/' folder)
project_root = full_path.parents[4]
sys.path.insert(0, str(project_root))
print("✅ Injected project root into sys.path:", project_root)

# ---------------------------------------------------------------------
# ✅ Imports AFTER sys.path is patched
# ---------------------------------------------------------------------
from backend.services.xai_service import get_top_tracks_from_xai
from backend.tests.test_utils import capture_logs_while_running, load_expected_data
from backend.config import TEST_JSON_DIR


# ---------------------------------------------------------------------
# 📋 Logging Configuration
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s]: %(message)s",
    force=True
)


# ---------------------------------------------------------------------
# 💡 Default test args (used if not running from CLI)
# ---------------------------------------------------------------------
args = argparse.Namespace(
    category="1960s",
    genre="rock",
    num_tracks=5,
    test_file_number=1
)

# ---------------------------------------------------------------------
# 🧪 CLI Argument Parsing
# ---------------------------------------------------------------------
if __name__ == "__main__" or "pytest" not in sys.modules:
    parser = argparse.ArgumentParser(description="Run XAI track test against a specific test JSON file")
    parser.add_argument("--category", type=str, default="1960s", help="Decade or category (e.g., '1960s')")
    parser.add_argument("--genre", type=str, default="rock", help="Music genre (e.g., 'rock')")
    parser.add_argument("--num_tracks", type=int, default=5, help="Number of top tracks to request")
    parser.add_argument("--test_file_number", type=int, default=1, help="Index of test file (e.g., 1 = json_test_file_1.json)")
    args = parser.parse_args()


# ---------------------------------------------------------------------
# 🔬 Core Test Function
# ---------------------------------------------------------------------
def run_test():
    logging.info(f"🔍 TESTING: {args.num_tracks} tracks in {args.genre} ({args.category}) [Test File #{args.test_file_number}]")

    # === Step 1: Call the function and capture logs
    result, logs = capture_logs_while_running(lambda: get_top_tracks_from_xai(
        category=args.category,
        genre=args.genre,
        language="English",
        num_tracks=args.num_tracks
    ))

    # === Step 2: Validate structure
    assert isinstance(result, dict), "❌ Returned value is not a dictionary"
    assert "tracks" in result, "❌ Missing 'tracks' key in returned result"
    actual_count = len(result["tracks"])

    # === Step 3: Load expectations
    test_file_path = TEST_JSON_DIR / f"json_test_file_{args.test_file_number}.json"
    expected_count, expected_logs = load_expected_data(test_file_path)

    # === Step 4: Validate track count
    assert actual_count == expected_count, (
        f"❌ Expected {expected_count} valid tracks, but got {actual_count}"
    )

    # === Step 5: Validate logs
    for expected_line in expected_logs:
        assert expected_line in logs, f"❌ Expected log line not found:\n{expected_line}"

    # ✅ Step 6: Output summary
    for track in result["tracks"]:
        logging.info(f"🎵 Rank {track.get('rank')}: {track.get('trackName')} by {track.get('artistName')}")


# ---------------------------------------------------------------------
# ✅ Pytest-Compatible Wrapper
# ---------------------------------------------------------------------
def test_get_top_tracks_from_xai_pytest():
    run_test()


# ---------------------------------------------------------------------
# 🚀 CLI Entrypoint
# ---------------------------------------------------------------------
if __name__ == "__main__":
    run_test()
