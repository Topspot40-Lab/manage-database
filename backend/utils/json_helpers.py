import os, json
from typing import Dict, Tuple, Optional

from backend.utils.logger_factory import get_step_logger  # ✅ Use your centralized logger

import traceback
import logging
import unicodedata
import re

logger = logging.getLogger(__name__)

# logger = get_step_logger("STEP_1.B")

# ─────────────────────────────────────────────────────────────────────────────
# 📁 JSON Path Constants
# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# 🎭 Artist Aliases
# ─────────────────────────────────────────────────────────────────────────────
ARTIST_NAME_ALIASES = {
    "Dixie Chicks": "The Chicks",
    "The Artist Formerly Known as Prince": "Prince",

    "Garth Brooks & Trisha Yearwood": "Garth Brooks",
    "Tim McGraw with Faith Hill": "Tim McGraw",
    "George Jones and Tammy Wynette": "George Jones",
    "Paul Simon and Art Garfunkel": "Simon and Garfunkel",
    "Simon and Garfunkel": "Simon and Garfunkel",

    "Elton John & Dua Lipa": "Elton John",
    "Brooks & Dunn": "Brooks & Dunn",
    "Huey Lewis and the News": "Huey Lewis & The News",

    "Selena y Los Dinos": "Selena",
    "The Chicks": "The Chicks",

    "Dave & Sugar": "Dave and Sugar",
    "Les Paul & Mary Ford": "Les Paul and Mary Ford",
    "Kenny Rogers & Dottie West": "Kenny Rogers and Dottie West",
    "Porter Wagoner & Dolly Parton": "Porter Wagoner and Dolly Parton",
    "James Taylor & Carly Simon": "James Taylor and Carly Simon",
    "George Jones & Tammy Wynette": "George Jones and Tammy Wynette",

    "Captain & Tennille": "Captain and Tennille",
    "Ike & Tina Turner": "Ike and Tina Turner",
    "Peter, Paul & Mary": "Peter, Paul and Mary",
}

# ─────────────────────────────────────────────────────────────────────────────
# 👥 Group + Duet Name Lists (normalized)
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_GROUPS = {
    "simon and garfunkel",
    "peter paul and mary",
    "brooks and dunn",
    "the byrds",
    "the beatles",
    "three dog night",
    "huey lewis and the news",
    "crosby stills nash",
    "crosby stills nash and young",
    "creedence clearwater revival",
}

KNOWN_DUET_PAIRS = {
    "ella fitzgerald louis armstrong",
    "tony bennett lady gaga",
    "johnny cash june carter",
    "george jones tammy wynette",
}


# ─────────────────────────────────────────────────────────────────────────────
# 🔧 Utilities
# ─────────────────────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    print(f"🔍 Calling normalize_name('{name}')")
    logger.debug(f"🔍 Calling normalize_name('{name}')")

    # Get the caller info (1 frame up the stack)
    stack = traceback.extract_stack()
    caller = stack[-2]  # -1 is this line, -2 is the caller
    print(f"   ↪️ Called from {caller.filename}:{caller.lineno} in {caller.name}")

    original = name.strip()
    corrected = ARTIST_NAME_ALIASES.get(original, original)

    corrected = unicodedata.normalize("NFKD", corrected)
    corrected = "".join(c for c in corrected if not unicodedata.combining(c))
    corrected = corrected.lower()
    corrected = corrected.replace(" and ", " ").replace("&", " ")
    corrected = re.sub(r"[^\w\s]", "", corrected)
    corrected = re.sub(r"\s+", " ", corrected).strip()

    if original != corrected:
        logger.debug(f"[STEP_1.B] normalize_name('{original}') → '{corrected}'")

    return corrected



def parse_featured_artists(raw_artist_name: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extract main and featured artist and the keyword used:
    e.g., 'Tim McGraw with Faith Hill' → ('Tim McGraw', 'Faith Hill', 'with')
    """
    pattern = r"(.*?)\s+(ft\.|feat\.|featuring|with)\s+(.*)"
    match = re.search(pattern, raw_artist_name, re.IGNORECASE)

    if match:
        main = match.group(1).strip()
        keyword = match.group(2).lower().strip()
        feat = match.group(3).strip()
        logger.debug(
            f"[STEP_1.B] parse_featured_artists('{raw_artist_name}') → main: '{main}', featured: '{feat}', keyword: '{keyword}'"
        )
        return main, feat, keyword

    logger.debug(f"[STEP_1.B] parse_featured_artists('{raw_artist_name}') → no featured artist found")
    return raw_artist_name.strip(), None, None

def get_mode_flag(artist_name: str) -> str:
    main, featured, keyword = parse_featured_artists(artist_name)
    normalized_main = normalize_name(main)

    # 🎤 Check if it's a known group
    if normalized_main in KNOWN_GROUPS:
        logger.debug(
            f"[STEP_1.B] get_mode_flag('{artist_name}') → 'group' "
            f"(matched KNOWN_GROUPS as '{normalized_main}')"
        )
        return "group"

    # 🎤 Handle duet or featured
    if featured:
        combined = normalize_name(f"{main} {featured}")
        if combined in KNOWN_DUET_PAIRS:
            logger.debug(
                f"[STEP_1.B] get_mode_flag('{artist_name}') → 'duet' "
                f"(matched KNOWN_DUET_PAIRS as '{combined}')"
            )
            return "duet"
        if keyword == "with":
            logger.debug(
                f"[STEP_1.B] get_mode_flag('{artist_name}') → 'duet' "
                f"(keyword='with')"
            )
            return "duet"
        logger.debug(
            f"[STEP_1.B] get_mode_flag('{artist_name}') → 'featured' "
            f"(keyword='{keyword}')"
        )
        return "featured"

    # 🎤 Default solo
    logger.debug(
        f"[STEP_1.B] get_mode_flag('{artist_name}') → 'solo' "
        "(no feature, no group match)"
    )
    return "solo"

# ─────────────────────────────────────────────────────────────────────────────
# 📁 File Loaders
# ─────────────────────────────────────────────────────────────────────────────
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
        json.dump(payload, f, indent=2)
