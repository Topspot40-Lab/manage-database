import os, json
from typing import Dict

JSON_BASE = "data/json_files/genredecade"

REQUIRED_FIELDS = [
    "rank", "trackName", "artistName", "durationMs", "trackId",
    "artistId", "albumArtwork", "intro", "detail", "yearReleased",
]

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
