import json
import re
import unicodedata
from typing import Dict, Tuple, Optional
from pathlib import Path

from backend.utils.logger_factory import get_step_logger

# 🔧 Constants
JSON_BASE = Path(__file__).resolve().parent.parent.parent / "data" / "json_files" / "genredecade"
logger_step1b = get_step_logger("STEP_1.B")

# ─────────────────────────────────────────────────────────────────────────────
# 📁 Required Fields
# ─────────────────────────────────────────────────────────────────────────────

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
    "Hank Snow & Anita Carter": "Hank Snow",
    "Hank Snow & Chet Atkins": "Hank Snow",
    "Hank Snow and The Rainbow Ranch Boys": "Hank Snow",
    "Hank Snow, Anita Carter & The Carter Family": "Hank Snow",
    "Hank Snow, The Singing Ranger, And His Rainbow Ranch Boys": "Hank Snow",
    "Hank Snow, The Singing Ranger & His Rainbow Ranch Boys": "Hank Snow",
    "Hank Snow, The Singing Ranger, and His Rainbow Ranch Boys": "Hank Snow",
}

# ─────────────────────────────────────────────────────────────────────────────
# 🎸 Known Groups by Genre
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_GROUPS = {
    "country": {
        "alabama", "the oak ridge boys", "the statler brothers", "the judds",
        "nitty gritty dirt band", "sawyer brown", "restless heart", "shenandoah",
        "the mavericks", "bellamy brothers", "little texas", "diamond rio",
        "lonestar", "rascal flatts", "lady a", "zac brown band", "the band perry",
        "blackhawk", "dixie chicks", "old dominion", "midland", "parmalee",
        "little big town", "eli young band", "florida georgia line", "brothers osborne",
        "high valley", "runaway june", "pistol annies", "home free"
    },
    "pop": {
        "the beatles", "the beach boys", "abba", "bee gees", "the supremes",
        "jackson 5", "earth wind and fire", "spice girls", "destinys child", "tlc",
        "boyz ii men", "backstreet boys", "nsync", "ace of base", "roxette",
        "eurythmics", "wham", "coldplay", "maroon 5", "imagine dragons",
        "one direction", "pentatonix", "little mix", "chainsmokers",
        "twenty one pilots", "bts", "blackpink"
    },
    "rock": {
        "rolling stones", "led zeppelin", "pink floyd", "queen", "the who",
        "the doors", "aerosmith", "eagles", "lynyrd skynyrd", "the clash", "u2",
        "acdc", "van halen", "journey", "bon jovi", "guns n roses", "metallica",
        "nirvana", "pearl jam", "red hot chili peppers", "rem", "radiohead",
        "green day", "foo fighters", "linkin park", "my chemical romance",
        "arctic monkeys", "the killers", "mumford and sons", "kings of leon"
    },
    "folk": {
        "simon and garfunkel", "peter paul and mary", "the kingston trio",
        "the weavers", "the byrds", "crosby stills nash",
        "crosby stills nash and young", "the lumineers", "mumford and sons",
        "of monsters and men", "fleet foxes", "the avett brothers", "punch brothers",
        "old crow medicine show", "first aid kit", "civil wars", "indigo girls"
    }
}

KNOWN_DUET_PAIRS = {
    "ella fitzgerald louis armstrong", "tony bennett lady gaga",
    "johnny cash june carter", "george jones tammy wynette"
}

# ─────────────────────────────────────────────────────────────────────────────
# 🔧 Utilities
# ─────────────────────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    original = name.strip()
    corrected = ARTIST_NAME_ALIASES.get(original, original)
    corrected = unicodedata.normalize("NFKD", corrected)
    corrected = "".join(c for c in corrected if not unicodedata.combining(c))
    corrected = corrected.lower()
    corrected = corrected.replace("&", " and")
    corrected = re.sub(r"[^\w\s]", "", corrected)
    corrected = re.sub(r"\s+", " ", corrected).strip()

    if original != corrected:
        logger_step1b.debug(f"normalize_name('{original}') → '{corrected}'")
    return corrected

def parse_featured_artists(raw_artist_name: str) -> Tuple[str, Optional[str], Optional[str]]:
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
    main_norm = normalize_name(main)
    feat_norm = normalize_name(feat) if feat else None
    logger_step1b.debug(f"[get_mode_flag] Checking artist mode — main: '{main}' → '{main_norm}', feat: '{feat}' → '{feat_norm}', keyword: '{keyword}'")
    for genre, group_set in KNOWN_GROUPS.items():
        if main_norm in group_set:
            logger_step1b.debug(f"[get_mode_flag] ✅ Matched known group → '{main_norm}' in genre '{genre}'")
            return "group"
    if feat_norm:
        combined = f"{main_norm} {feat_norm}"
        if combined in KNOWN_DUET_PAIRS:
            logger_step1b.debug(f"[get_mode_flag] ✅ Matched known duet → '{combined}'")
            return "duet"
        if keyword == "with":
            logger_step1b.debug(f"[get_mode_flag] ✅ Keyword 'with' detected → treating as duet")
            return "duet"
        logger_step1b.debug(f"[get_mode_flag] ✅ Featured artist → keyword: '{keyword}'")
        return "featured"
    logger_step1b.debug(f"[get_mode_flag] Defaulting to 'solo'")
    return "solo"

# ─────────────────────────────────────────────────────────────────────────────
# 📁 JSON File Loaders / Savers
# ─────────────────────────────────────────────────────────────────────────────

def load_full_json_file(decade: Optional[str] = None, filename: Optional[str] = None, *, file_path: Optional[Path] = None) -> Dict:
    """
    Load a full TopSpot JSON file from either:
      - `file_path`, or
      - `decade` + `filename` from the known genredecade directory
    """
    if file_path:
        path = file_path
        context = f"[Direct path: {file_path.name}]"
    elif decade and filename:
        path = JSON_BASE / decade / filename
        context = f"[From decade: {decade}, file: {filename}]"
    else:
        raise ValueError("Must provide either file_path or (decade and filename)")

    logger_step1b.info(f"📁 Loading JSON {context}")
    logger_step1b.debug(f"🔍 Full path: {path.resolve()}")

    if not path.exists():
        logger_step1b.error(f"❌ File not found: {path}")
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    top_keys = list(data.keys())
    track_count = len(data.get("ranking_tables", {}).get("track_ranking", []))
    logger_step1b.info(f"✅ Loaded JSON: {len(top_keys)} top-level keys, {track_count} track(s)")

    tracks = data.get("track_tables", {}).get("track", [])
    if tracks:
        logger_step1b.debug(f"🧪 Sample intro (rank {tracks[0].get('rank')}): {tracks[0].get('intro')}")

    return data

def save_full_json_file(payload: Dict, decade: str, filename: str):
    """
    Save a full TopSpot JSON dictionary to the genredecade directory.
    """
    path = JSON_BASE / decade
    path.mkdir(parents=True, exist_ok=True)

    full_path = path / filename
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    logger_step1b.info(f"💾 Saved JSON file: {full_path.name}")
    logger_step1b.debug(f"📁 Save path: {full_path.resolve()}")
