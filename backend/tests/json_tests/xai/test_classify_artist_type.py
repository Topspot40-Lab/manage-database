import sys
from pathlib import Path
import logging
import json

# 🧭 Locate and inject the project root (4 levels up from this test file)
full_path = Path(__file__).resolve()
project_root = full_path.parents[4]  # This should be 'topspot_json_creator'
sys.path.insert(0, str(project_root))
print("✅ Injected project root into sys.path:", project_root)

# ✅ Now import your filter
from backend.utils.track_filters import classify_artist_type


# 📂 Path to JSON test files
TEST_JSON_DIR = Path("backend/tests/json_tests/xai")


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
)


def run_classification_test(test_file_number: int = 5):
    test_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
    logging.info(f"📁 Starting classification test using {test_path}")

    with open(test_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    genre = data.get("genre") or data.get("core_tables", {}).get("genre", [{}])[0].get("genre_name", "unknown")
    tracks = data.get("tracks", [])

    print(f"\n🎷 Genre context: {genre}")
    print(f"🎼 Found {len(tracks)} tracks. Starting classification...\n")

    for i, track in enumerate(tracks, 1):
        artist = track.get("artistName") or track.get("artist_name", "???")
        title = track.get("trackName") or track.get("track_name", "???")

        result = classify_artist_type(artist, genre)
        print(f"{i:2d}: 🎵 '{title}' by '{artist}' → 🎭 {result}")


if __name__ == "__main__":
    run_classification_test()
