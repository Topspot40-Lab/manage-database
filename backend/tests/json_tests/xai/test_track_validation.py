import json
import logging
from pathlib import Path
import pytest

from backend.services.xai_response_handler import parse_and_filter_tracks
from backend.tests.test_utils import capture_logs_while_running

# -----------------------------------------------------------------------------
# 📁 Directory where your JSON test files are stored
# -----------------------------------------------------------------------------
TEST_DIR = Path("backend/tests/json_tests/xai")

# -----------------------------------------------------------------------------
# 🔍 Dynamically collect test file numbers based on filenames
# Returns a list like [1, 2, 3, ...] for json_test_file_1.json, etc.
# -----------------------------------------------------------------------------
def get_test_file_numbers():
    return sorted([
        int(p.name.split("_")[-1].split(".")[0])
        for p in TEST_DIR.glob("json_test_file_*.json")
    ])

# -----------------------------------------------------------------------------
# ✅ Parametrized test that runs for each numbered test file
# Validates both:
#   1. Number of valid tracks returned
#   2. Expected log output presence
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("test_file_number", get_test_file_numbers())
def test_json_file(test_file_number):
    test_file_path = TEST_DIR / f"json_test_file_{test_file_number}.json"

    logging.info(f"\n\n🧪 Starting test for: {test_file_path}\n")

    # Load test data from file
    with open(test_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tracks = data["tracks"]
    raw_json = json.dumps(tracks)

    expected_count = data.get("expected", {}).get("numValidTracks", len(tracks))
    expected_logs = data.get("expectedLogs", [])

    logging.info(f"🔢 Expected valid tracks: {expected_count}")
    logging.info(f"📋 Expected log fragments: {len(expected_logs)} entries")

    # Wrap the function call to capture logs
    def run_test():
        return parse_and_filter_tracks(raw_json, num_tracks=expected_count, is_test_mode=True)

    result, logs = capture_logs_while_running(run_test)

    # ✅ Assert the number of valid tracks
    assert len(result) == expected_count, (
        f"❌ Test file {test_file_number}: Expected {expected_count} tracks, got {len(result)}"
    )

    logging.info(f"✅ Returned valid tracks: {len(result)}")

    # ✅ Assert expected logs were captured
    for expected_log in expected_logs:
        assert expected_log in logs, f"❌ Missing expected log in file {test_file_number}: '{expected_log}'"
        logging.info(f"✔️ Found expected log: {expected_log}")

    logging.info(f"✅ Test file {test_file_number} PASSED successfully.\n")
