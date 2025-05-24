import os, json
import re
from typing import Dict

JSON_BASE = "data/json_files/genredecade"

REQUIRED_FIELDS = [
    "rank", "trackName", "artistName", "durationMs", "trackId",
    "artistId", "albumArtwork", "intro", "detail", "yearReleased",
]


def parse_featured_artists(raw_artist_name: str):
    """
    Extracts main artist and featured artist from a name like:
    '50 Cent ft. Olivia' → ('50 Cent', 'Olivia')
    'Beyoncé feat. Jay-Z' → ('Beyoncé', 'Jay-Z')
    If no featured artist is found, returns (raw_artist_name, None)
    """
    match = re.search(r"(.*?)\s+(?:ft\.|feat\.)\s+(.*)", raw_artist_name, re.IGNORECASE)
    if match:
        main_artist = match.group(1).strip()
        featured_artist = match.group(2).strip()
        return main_artist, featured_artist
    return raw_artist_name.strip(), None



def load_json(decade: str, filename: str) -> Dict:
    path = os.path.join(JSON_BASE, decade, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(payload: Dict, decade: str, filename: str):
    path = os.path.join(JSON_BASE, decade)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, filename), "w", encoding="utf-8") as f:
        # noinspection PyTypeChecker
        json.dump(payload, f, indent=2)
