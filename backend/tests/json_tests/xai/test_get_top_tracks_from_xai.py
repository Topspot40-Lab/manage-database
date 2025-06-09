"""
📄 Test Script: test_get_top_tracks_from_xai.py

This script tests the `get_top_tracks_from_xai()` function using structured JSON test files
and log verification. It can be executed in two ways:

1. ✅ As a standalone Python script (run manually with CLI args)
2. ✅ As a `pytest`-compatible test suite (auto-discovers `test_*` functions)

The test validates:
- That a dictionary with a 'tracks' key is returned
- That the number of valid tracks matches expected test data
- That expected log lines were emitted during execution

Test input and expectations are controlled entirely by a JSON test file.

🦪as Only one command-line argument is required:
- --test_file_number → Index of test file (e.g., 1 = json_test_file_1.json)

📿 Test file format should include:
- "genre", "category" (decade), "language", and "tracks" array
- "expected" section (e.g., numValidTracks)
- "expectedLogs" list for verifying log output

🎯 Example CLI Usage:
python backend/tests/json_tests/xai/test_get_top_tracks_from_xai.py --test_file_number 1
"""

import json
import sys
import logging
from pathlib import Path
import argparse

# 🔍 Dynamically find the project root and inject it into sys.path
full_path = Path(__file__).resolve()
print("📜 Full path to test file:", full_path)

# 🔧 Correct project root (should contain the 'backend/' folder)
project_root = full_path.parents[4]
sys.path.insert(0, str(project_root))
print("✅ Injected project root into sys.path:", project_root)

# ✅ Imports AFTER sys.path is patched
from backend.services.xai_service import get_top_tracks_from_xai
from backend.tests.test_utils import capture_logs_while_running, load_expected_data
from backend.config import TEST_JSON_DIR

# 📋 Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    force=True
)

logging.info(f"📁 Test started in: {__file__}")

# 🦪as CLI Argument Parsing or Fallback
if __name__ == "__main__" or "pytest" not in sys.modules:
    parser = argparse.ArgumentParser(description="Run XAI track test against a specific test JSON file")
    parser.add_argument("--test_file_number", type=int, default=1,
                        help="Index of test file (e.g., 1 = json_test_file_1.json)")
    args = parser.parse_args()
else:
    # ✅ Default fallback values used by pytest
    args = argparse.Namespace(
        test_file_number=1
    )

# 🔬 Core Test Function
def run_test():
    # === Special LIVE MODE: Run with no JSON test file ===
    if args.test_file_number == 0:
        print("\n🔴 LIVE MODE (test_file_number=0): No JSON test file will be used.\n")
        decade = input("Enter decade (e.g. 1980s): ").strip()
        genre = input("Enter genre (e.g. country): ").strip()
        num_tracks = int(input("Enter number of tracks: ").strip())
        language = "English"

        # Call XAI with live data and capture logs
        result, logs = capture_logs_while_running(lambda: get_top_tracks_from_xai(
            decade=decade,
            genre=genre,
            language=language,
            num_tracks=num_tracks,
            test_file_number=0
        ))

        # Basic structure checks
        assert isinstance(result, dict), "❌ Returned value is not a dictionary"
        assert "tracks" in result, "❌ Missing 'tracks' key in returned result"
        actual_count = len(result["tracks"])
        assert actual_count == num_tracks, f"❌ Expected {num_tracks} tracks, got {actual_count}"

        print(f"\n✅ LIVE TEST PASSED: Returned {actual_count} tracks from XAI\n")

        # Show summary of duets, features, etc.
        for track in result["tracks"]:
            name = track.get("trackName")
            artist = track.get("artistName")
            rank = track.get("rank", "?")
            print(f"🎵 {rank}: {name} by {artist}")

            artist_lower = artist.lower()
            if " with " in artist_lower:
                print(f"   👥 DUET detected: {artist}")
            elif " feat" in artist_lower or " ft." in artist_lower:
                print(f"   ⭐ FEATURED artist detected: {artist}")
            elif " & " in artist:
                print(f"   🎤 GROUP or collaboration detected: {artist}")

        print("\n🗒 Log messages:")
        print(logs)
        return

    # === Standard TEST MODE: Load expectations from test file ===
    test_file_path = TEST_JSON_DIR / f"json_test_file_{args.test_file_number}.json"
    expected_count, expected_logs = load_expected_data(test_file_path)

    with open(test_file_path, "r", encoding="utf-8") as f:
        test_json = json.load(f)
        real_decade = test_json.get("category", "1960s")
        real_genre = test_json.get("genre", "rock")
        real_num_tracks = len(test_json.get("tracks", []))

    logging.info(
        f"🔍 TESTING: {real_num_tracks} tracks in {real_genre} ({real_decade}) [Test File #{args.test_file_number}]"
    )

    result, logs = capture_logs_while_running(lambda: get_top_tracks_from_xai(
        decade=real_decade,
        genre=real_genre,
        language=test_json.get("language", "English"),
        num_tracks=real_num_tracks,
        test_file_number=args.test_file_number
    ))

    assert isinstance(result, dict), "❌ Returned value is not a dictionary"
    assert "tracks" in result, "❌ Missing 'tracks' key in returned result"
    actual_count = len(result["tracks"])
    assert actual_count == expected_count, (
        f"❌ Expected {expected_count} valid tracks, but got {actual_count}"
    )

    logs_normalized = [line.lower() for line in logs.splitlines()]
    for expected_line in expected_logs:
        assert expected_line.lower() in logs_normalized, f"❌ Expected log line not found:\n{expected_line}"

    for track in result["tracks"]:
        logging.info(f"🎵 Rank {track.get('rank')}: {track.get('trackName')} by {track.get('artistName')}")

    test_file_name = f"json_test_file_{args.test_file_number}.json"
    logging.info("✅ All validations passed for %s (%s - %s)", test_file_name, real_decade, real_genre)
    print(f"\n✅ TEST PASSED: All validations completed successfully for file: {test_file_name}\n")

# ✅ Pytest-Compatible Wrapper
def test_get_top_tracks_from_xai_pytest():
    run_test()

# 🚀 CLI Entrypoint
if __name__ == "__main__":
    run_test()
