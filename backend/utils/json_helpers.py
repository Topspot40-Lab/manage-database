import os, json
import re
import unicodedata
from typing import Dict
import logging

logger = logging.getLogger(__name__)

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
    # ✅ Legacy group name → modern Spotify name
    "Dixie Chicks": "The Chicks",

    # ✅ Artist aliases or rebrands
    "The Artist Formerly Known as Prince": "Prince",

    # ✅ Duets often filed under solo artist
    "Garth Brooks & Trisha Yearwood": "Garth Brooks",
    "Tim McGraw with Faith Hill": "Tim McGraw",
    "George Jones and Tammy Wynette": "George Jones",
    "Paul Simon and Art Garfunkel": "Simon and Garfunkel",
    "Simon and Garfunkel": "Simon and Garfunkel",  # for completeness

    # ✅ Avoid group misinterpretation
    "Elton John & Dua Lipa": "Elton John",
    "Brooks & Dunn": "Brooks & Dunn",  # don't change this one
    "Huey Lewis and the News": "Huey Lewis & The News",


    # ✅ Latin music edge case
    "Selena y Los Dinos": "Selena",

    # ✅ Just in case "The Chicks" are the name used already
    "The Chicks": "The Chicks",

    "Dave & Sugar": "Dave and Sugar",
    "Les Paul & Mary Ford": "Les Paul and Mary Ford",
    "Kenny Rogers & Dottie West": "Kenny Rogers and Dottie West",
    "Porter Wagoner & Dolly Parton": "Porter Wagoner and Dolly Parton",
    "James Taylor & Carly Simon": "James Taylor and Carly Simon",
    "George Jones & Tammy Wynette": "George Jones and Tammy Wynette",  # Consistency

    # For Spotify's preferences
    "Captain & Tennille": "Captain and Tennille",
    "Ike & Tina Turner": "Ike and Tina Turner",
    "Peter, Paul & Mary": "Peter, Paul and Mary",

    # Add any you catch in log warnings
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

    corrected = ARTIST_NAME_ALIASES.get(name, name)

    if name != corrected:
        logger.info(f"🎭 Alias applied: '{name}' → '{corrected}'")

    return corrected

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
