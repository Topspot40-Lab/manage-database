# backend/tests/json_tests/xai/test_get_top_tracks_from_xai.py

import sys
import logging
import argparse
# import pytest
from backend.services.xai_service import get_top_tracks_from_xai

# Setup logging with module and fun
#
# ction names
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s]: %(message)s",
    force=True
)

# Default values (in case not passed via CLI)
args = argparse.Namespace(decade="1960s", genre="rock", num_tracks=3)

# Allow passing CLI arguments if not in pytest discovery mode
if __name__ == "__main__" or "pytest" not in sys.modules:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decade", type=str, default="1960s", help="Decade, e.g. '1960s'")
    parser.add_argument("--genre", type=str, default="rock", help="Genre, e.g. 'rock'")
    parser.add_argument("--num_tracks", type=int, default=3, help="Number of tracks to fetch")
    args = parser.parse_args()


def test_get_top_tracks_from_xai():
    """Test the XAI track generation with hardcoded input."""
    decade = "2000s"
    genre = "rock"
    num_tracks = 30

    logging.info(f"🔍 TESTING: XAI for {num_tracks} tracks in {genre} during {decade}")

    data = get_top_tracks_from_xai(
        category=decade,
        genre=genre,
        language="English",
        num_tracks=num_tracks
    )

    assert isinstance(data, dict)
    assert "tracks" in data
    assert len(data["tracks"]) == num_tracks

    for track in data["tracks"]:
        logging.info(
            f"🎵 Rank {track.get('rank')}: {track.get('trackName')} by {track.get('artistName')} "
            f"({track.get('yearReleased')})"
        )