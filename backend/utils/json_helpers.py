import os, json
import re
import unicodedata
from typing import Dict

JSON_BASE = "data/json_files/genredecade"

REQUIRED_FIELDS = [
    "track_name",
    "artist_name",
    "duration_ms",
    "track_id",
    "artist_id",
    "album_artwork",
    "detail",
    "year_released"
]


# Add alias mappings for renamed artists or known edge cases
ARTIST_NAME_ALIASES = {
    "Dixie Chicks": "The Chicks",
    "Prince": "The Artist Formerly Known as Prince",
    # Add more here as needed
}

def normalize_name(name: str) -> str:
    """
    Normalize a name by:
    - Stripping accents
    - Removing extra whitespace
    - Applying known alias corrections
    """
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.strip()

    # Apply alias override if one exists
    return ARTIST_NAME_ALIASES.get(name, name)

def parse_featured_artists(raw_artist_name: str):
    """
    Extracts the main artist and featured artist from a name like:
    - 'Beyoncé feat. Jay-Z' → ('Beyoncé', 'Jay-Z')
    - 'Tim McGraw with Faith Hill' → ('Tim McGraw', 'Faith Hill')
    - 'Elton John & Dua Lipa' → ('Elton John', 'Dua Lipa')
    - 'Queen and David Bowie' → ('Queen', 'David Bowie')
    If no featured/collab is found, returns (raw_artist_name, None)
    """
    # Took out the "&" symbol for group names like "Brooks & Dunn".
    # pattern = r"(.*?)\s+(?:ft\.|feat\.|featuring|with|&|and)\s+(.*)"

    # Removed "&" because of conflict with 'Brooks & Dunn' and 'Elton John & Dua Lipa'
    pattern = r"(.*?)\s+(?:ft\.|feat\.|featuring|with|and)\s+(.*)"

    match = re.search(pattern, raw_artist_name, re.IGNORECASE)
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
