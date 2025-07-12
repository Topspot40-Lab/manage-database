import os, json
from typing import Dict, Tuple, Optional

import traceback
import unicodedata
import re

from backend.utils.logger_factory import get_step_logger

# Use centralized step logger
logger_step1b = get_step_logger("STEP_1.B")

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

    # 🎵 Hank Snow aliases
    "Hank Snow & Anita Carter": "Hank Snow",
    "Hank Snow & Chet Atkins": "Hank Snow",
    "Hank Snow and The Rainbow Ranch Boys": "Hank Snow",
    "Hank Snow, Anita Carter & The Carter Family": "Hank Snow",
    "Hank Snow, The Singing Ranger, And His Rainbow Ranch Boys": "Hank Snow",
    "Hank Snow, The Singing Ranger & His Rainbow Ranch Boys": "Hank Snow",
    "Hank Snow, The Singing Ranger, and His Rainbow Ranch Boys": "Hank Snow",
}

# ─────────────────────────────────────────────────────────────────────────────
# 🎸 KNOWN GROUPS WITH TOP‑40 HITS (1950s → present)
#   • Keys  = genre
#   • Values = {normalized group names}
#   • Update whenever you run into a new mis‑detected group.
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_GROUPS = {
    "country": {
        # 1960s‑80s pioneers
        "alabama",
        "the oak ridge boys",
        "the statler brothers",
        "the judds",
        "nitty gritty dirt band",
        "sawyer brown",
        "restless heart",
        "shenandoah",
        "the mavericks",
        "bellamy brothers",

        # 1990s‑2000s mainstream
        "little texas",
        "diamond rio",
        "lonestar",
        "rascal flatts",
        "lady a",
        "zac brown band",
        "the band perry",
        "blackhawk",
        "dixie chicks",   # 😎 include alias; your alias‑map can remap → “the chicks”

        # 2010s‑present
        "old dominion",
        "midland",
        "parmalee",
        "little big town",
        "eli young band",
        "florida georgia line",
        "brothers osborne",
        "high valley",
        "runaway june",
        "pistol annies",
        "home free",
    },

    "pop": {
        # 1960s‑70s classics
        "the beatles",
        "the beach boys",
        "abba",
        "bee gees",
        "the supremes",
        "jackson 5",
        "earth wind and fire",

        # 1980s‑90s radio staples
        "spice girls",
        "destinys child",
        "tlc",
        "boyz ii men",
        "backstreet boys",
        "nsync",
        "ace of base",
        "roxette",
        "eurythmics",
        "wham",

        # 2000s‑present chart giants
        "coldplay",
        "maroon 5",
        "imagine dragons",
        "one direction",
        "pentatonix",
        "little mix",
        "chainsmokers",
        "twenty one pilots",
        "bts",                 # counts as group even if k‑pop
        "blackpink",
    },

    "rock": {
        # 1960s‑70s icons
        "rolling stones",
        "led zeppelin",
        "pink floyd",
        "queen",
        "the who",
        "the doors",
        "aerosmith",
        "eagles",
        "lynyrd skynyrd",
        "the clash",
        "u2",

        # 1980s‑90s
        "acdc",
        "van halen",
        "journey",
        "bon jovi",
        "guns n roses",
        "metallica",
        "nirvana",
        "pearl jam",
        "red hot chili peppers",
        "rem",
        "radiohead",
        "green day",
        "foo fighters",

        # 2000s‑present
        "linkin park",
        "my chemical romance",
        "arctic monkeys",
        "the killers",
        "mumford and sons",
        "imagine dragons",   # also pop/alt
        "kings of leon",
    },

    "folk": {
        # folk & folk‑rock trailblazers
        "simon and garfunkel",
        "peter paul and mary",
        "the kingston trio",
        "the weavers",
        "the byrds",
        "crosby stills nash",
        "crosby stills nash and young",

        # modern folk/folk‑pop
        "the lumineers",
        "mumford and sons",
        "of monsters and men",
        "fleet foxes",
        "the avett brothers",
        "punch brothers",
        "old crow medicine show",
        "first aid kit",
        "civil wars",
        "indigo girls",
    },
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
    # logger_step1b.debug(f"🔍 Calling normalize_name('{name}')")

    # Get the caller info (optional for debug tracing)
    # stack = traceback.extract_stack()
    # caller = stack[-2]  # -1 is this line, -2 is the caller
    # print(f"   ↪️ Called from {caller.filename}:{caller.lineno} in {caller.name}")

    original = name.strip()

    # 🎭 Alias substitution (before any other processing)
    if original in ARTIST_NAME_ALIASES:
        alias = ARTIST_NAME_ALIASES[original]
        logger_step1b.debug(f"🎭 Alias substitution: '{original}' → '{alias}'")
        corrected = alias
    else:
        corrected = original

    # 🎨 Normalization: accents, punctuation, case
    corrected = unicodedata.normalize("NFKD", corrected)
    corrected = "".join(c for c in corrected if not unicodedata.combining(c))
    corrected = corrected.lower()
    corrected = corrected.replace("&", " and")  # ✅ Normalize '&' but keep 'and'
    corrected = re.sub(r"[^\w\s]", "", corrected)
    corrected = re.sub(r"\s+", " ", corrected).strip()

    # 📝 Final normalization log if changed
    if original != corrected:
        logger_step1b.debug(f"normalize_name('{original}') → '{corrected}'")

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
        logger_step1b.debug(f"parse_featured_artists('{raw_artist_name}') → main: '{main}', featured: '{feat}', keyword: '{keyword}'")
        return main, feat, keyword

    logger_step1b.debug(f"parse_featured_artists('{raw_artist_name}') → no featured artist found")
    return raw_artist_name.strip(), None, None
def get_mode_flag(main: str, feat: Optional[str], keyword: Optional[str]) -> str:
    """
    Determine mode_flag type based on normalized artist parts.
    Handles test mode gracefully by scanning all known groups across genres.
    """

    main_norm = normalize_name(main)
    feat_norm = normalize_name(feat) if feat else None

    logger_step1b.debug(
        f"[get_mode_flag] Checking artist mode — main: '{main}' → '{main_norm}', "
        f"feat: '{feat}' → '{feat_norm}', keyword: '{keyword}'"
    )

    # ✅ Scan all known groups (across all genres — works in test mode)
    for genre, group_set in KNOWN_GROUPS.items():
        if main_norm in group_set:
            logger_step1b.debug(
                f"[get_mode_flag] ✅ Matched known group → '{main_norm}' in genre '{genre}'"
            )
            return "group"

    # 🎤 Check duet / feature
    if feat_norm:
        combined = f"{main_norm} {feat_norm}"
        if combined in KNOWN_DUET_PAIRS:
            logger_step1b.debug(
                f"[get_mode_flag] ✅ Matched known duet → '{combined}' in KNOWN_DUET_PAIRS"
            )
            return "duet"
        if keyword == "with":
            logger_step1b.debug(
                f"[get_mode_flag] ✅ Keyword 'with' detected → treating as duet"
            )
            return "duet"
        logger_step1b.debug(
            f"[get_mode_flag] ✅ Featured artist pattern detected → keyword: '{keyword}'"
        )
        return "featured"

    # 🎙️ Default to solo
    logger_step1b.debug(
        f"[get_mode_flag] No group or feature match → defaulting to 'solo'"
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
