import json
from pathlib import Path

# Example base directory — adjust if needed
from backend.config import BASE_DIR

BASE_JSON_DIR = BASE_DIR / "data" / "json_files" / "genredecade"



def get_track_file_path(genre: str, decade: str) -> Path:
    """
    Build the full file path based on genre and decade.
    """
    genre = genre.lower().replace(" ", "_")
    decade = decade.lower()
    filename = f"{decade}_{genre}_en.json"
    full_path = BASE_JSON_DIR / decade / filename
    return full_path

def load_json_track_file(genre: str, decade: str) -> list:
    """
    Load the JSON track data from disk and return the track list.
    """
    file_path = get_track_file_path(genre, decade)

    if not file_path.exists():
        raise FileNotFoundError(f"Track file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    tracks = data.get("track", [])

    if not tracks:
        raise ValueError(f"No tracks found in file: {file_path}")

    return tracks
