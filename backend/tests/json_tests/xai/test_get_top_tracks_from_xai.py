# backend/tests/json_tests/xai/test_get_top_tracks_from_xai.py

import sys
import logging
import argparse
from backend.services.xai_service import get_top_tracks_from_xai

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s]: %(message)s",
    force=True
)

# Default CLI arguments
args = argparse.Namespace(category="1960s", genre="rock", num_tracks=3)

# Allow CLI override if run directly (not during pytest)
if __name__ == "__main__" or "pytest" not in sys.modules:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", type=str, default="1960s", help="Decade/Category, e.g. '1960s'")
    parser.add_argument("--genre", type=str, default="rock", help="Genre, e.g. 'rock'")
    parser.add_argument("--num_tracks", type=int, default=3, help="Number of tracks to fetch")
    args = parser.parse_args()

def run_test():
    logging.info(f"🔍 TESTING: XAI for {args.num_tracks} tracks in {args.genre} during {args.category}")

    data = get_top_tracks_from_xai(
        category=args.category,
        genre=args.genre,
        language="English",
        num_tracks=args.num_tracks
    )

    assert isinstance(data, dict)
    assert "tracks" in data
    assert len(data["tracks"]) == args.num_tracks

    for track in data["tracks"]:
        logging.info(
            f"🎵 Rank {track.get('rank')}: {track.get('trackName')} by {track.get('artistName')} "
            f"({track.get('yearReleased')})"
        )

# === Pytest-compatible test function ===
def test_get_top_tracks_from_xai_pytest():
    run_test()

# === Allow running directly from CLI ===
if __name__ == "__main__":
    run_test()
