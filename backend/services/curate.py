# backend/services/curate.py
from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Optional, TypedDict, Any, Tuple

from backend.services.xai_api_client import fetch_xai_tracks  # ✅ your client

logger = logging.getLogger("curate")


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────

class SeedTrack(TypedDict, total=False):
    title: str
    artist: str
    year: Optional[int]


# ─────────────────────────────────────────────────────────────────────────────
# Theme registry: names, slugs, aliases
#   - call curate_tracks_via_xai(theme="power_ballads") OR theme="Power Ballads"
# ─────────────────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s

# Canonical display name per slug
THEMES: Dict[str, str] = {
    "disney_classics_pre_1988": "Disney: Classics (pre-1988)",
    "disney_revival_after_1988": "Disney: Revival (after-1988)",
    "classical_music_baroque_period_1600_1750": "Classical Music: Baroque Period (1600-1750)",
    "classical_music_classical_period_1750_1820": "Classical Music: Classical Period (1750-1820)",
    "classical_music_romantic_period_1820_1910": "Classical Music: Romantic Period (1820-1910)",
    "power_ballads": "Power Ballads",
    "motown_magic": "Motown Magic",
    "disco_favorites": "Disco Favorites",
    "one_hit_wonders": "One-Hit Wonders",
    "stage_screen_broadway_classics": "Stage & Screen: Broadway Classics",
    "stage_screen_movie_themes": "Stage & Screen: Movie Themes",
    "dance_floor_anthems": "Dance Floor Anthems",
    "protest_social_justice": "Protest & Social Justice",
    "latin_crossovers": "Latin Crossovers",
    "holiday_favorites": "Holiday Favorites",
    "novelty_songs": "Novelty Songs",
    "video_game_themes": "Video Game Themes",
    "country_duets": "Country Duets",
    "pop_duets": "Pop Duets"
    # add your new ones here...
}

# Aliases (display name -> canonical display name)
ALIASES_BY_NAME: Dict[str, str] = {
    "Protest & Social Anthems": "Protest & Social Justice",
    # add more as needed
}

def _resolve_theme_name_or_slug(theme: str) -> Tuple[str, str]:
    """
    Returns (slug, display_name).
    Accepts either a slug ("power_ballads") or a display name ("Power Ballads").
    Applies ALIASES_BY_NAME when given a display name.
    """
    if theme in THEMES:
        return theme, THEMES[theme]

    # Try display name
    disp = ALIASES_BY_NAME.get(theme, theme)
    slug = _slugify(disp)
    if slug in THEMES:
        return slug, THEMES[slug]

    # Fallback: accept unknown, but keep consistent slug
    return _slugify(theme), disp


# ─────────────────────────────────────────────────────────────────────────────
# Prompt templates
# ─────────────────────────────────────────────────────────────────────────────

# Per-theme custom prompts (optional). Fallback to DEFAULT_PROMPT if missing.
PROMPTS: Dict[str, str] = {
    "power_ballads": (
        'Curate {max_items} definitive "Power Ballads" mixing late-70s–90s rock ballads. '
        'Avoid karaoke/tribute/instrumental versions. '
        'Return ONLY a JSON array of objects with keys: "title", "artist", "year".'
    ),
    "motown_magic": (
        'Curate {max_items} essential Motown hits across the 60s–70s. '
        'Prioritize original Motown label releases. Avoid live/alt takes unless iconic. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "disco_favorites": (
        'Curate {max_items} disco classics (mid-70s to early-80s). '
        'Favor studio originals; avoid remixes unless historically canonical. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "one_hit_wonders": (
        'Curate {max_items} iconic one-hit wonders (US/UK focus). '
        'Prefer the artist’s singular chart-defining hit. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "stage_screen_broadway_classics": (
        'Curate {max_items} Broadway classics (original cast or definitive revivals). '
        'Include show title in parentheses in the "title" when obvious (optional). '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "stage_screen_movie_themes": (
        'Curate {max_items} famous movie themes and title songs across decades. '
        'Prefer original soundtrack versions. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "dance_floor_anthems": (
        'Curate {max_items} dance-floor anthems spanning eras (disco, house, EDM, pop). '
        'Must be widely recognized club staples. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "protest_social_justice": (
        'Curate {max_items} protest & social justice songs across decades and genres. '
        'Favor tracks with clear historical/cultural impact. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "latin_crossovers": (
        'Curate {max_items} Latin crossover hits that reached broad international audiences. '
        'Include Spanish/English/Portuguese as relevant. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "holiday_favorites": (
        'Curate {max_items} holiday favorites (mostly Christmas, some Hanukkah/New Year if iconic). '
        'Prefer definitive recordings. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "novelty_songs": (
        'Curate {max_items} novelty/novelty-adjacent songs that charted or became culturally famous. '
        'Avoid children-only niche unless massively recognized. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "video_game_themes": (
        'Curate {max_items} iconic video game themes and songs (original or definitive arranged versions). '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "country_duets": (
        'Curate {max_items} classic and modern country duets. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "pop_duets": (
        'Curate {max_items} pop duets across decades, emphasizing chemistry and chart impact. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "disney_classics_pre_1988": (
        'Curate {max_items} Disney classics up to and including 1987. '
        'Prefer original soundtrack/cast recordings. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "disney_revival_after_1988": (
        'Curate {max_items} Disney Revival era hits from 1988 onward. '
        'Prefer original soundtrack/cast recordings. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "classical_music_baroque_period_1600_1750": (
        'Curate {max_items} Baroque pieces (1600–1750) by canonical composers. '
        'Use the movement/work title in "title" and principal artist in "artist". '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "classical_music_classical_period_1750_1820": (
        'Curate {max_items} Classical period pieces (1750–1820). '
        'Use the work/movement for "title", principal artist for "artist", year of composition if known. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
    "classical_music_romantic_period_1820_1910": (
        'Curate {max_items} Romantic period pieces (1820–1910). '
        'Use the work/movement for "title", principal artist for "artist", year of composition if known. '
        'Return ONLY JSON objects: "title","artist","year".'
    ),
}

DEFAULT_PROMPT = (
    'Curate {max_items} definitive tracks for the theme "{display_name}". '
    'Avoid karaoke/tribute/instrumental versions. '
    'Return ONLY a JSON array of objects with keys: "title", "artist", "year".'
)


# ─────────────────────────────────────────────────────────────────────────────
# Seeds (optional fallback when XAI returns nothing)
# ─────────────────────────────────────────────────────────────────────────────
SEEDS_BY_SLUG: Dict[str, List[SeedTrack]] = {
    "disney_classics_pre_1988": [
        {"title": "When You Wish Upon a Star", "artist": "Cliff Edwards", "year": 1940},
        {"title": "A Dream Is a Wish Your Heart Makes", "artist": "Ilene Woods", "year": 1950},
        {"title": "Heigh-Ho", "artist": "The Dwarf Chorus", "year": 1937},
    ],
    "disney_revival_after_1988": [
        {"title": "Part of Your World", "artist": "Jodi Benson", "year": 1989},
        {"title": "A Whole New World", "artist": "Lea Salonga & Brad Kane", "year": 1992},
        {"title": "Let It Go", "artist": "Idina Menzel", "year": 2013},
    ],
    "classical_music_baroque_period_1600_1750": [
        {"title": "Brandenburg Concerto No. 3", "artist": "J. S. Bach", "year": 1721},
        {"title": "The Four Seasons: Spring", "artist": "Antonio Vivaldi", "year": 1725},
        {"title": "Dido and Aeneas: When I Am Laid in Earth", "artist": "Henry Purcell", "year": 1689},
    ],
    "classical_music_classical_period_1750_1820": [
        {"title": "Eine kleine Nachtmusik", "artist": "Wolfgang Amadeus Mozart", "year": 1787},
        {"title": "Symphony No. 5", "artist": "Ludwig van Beethoven", "year": 1808},
        {"title": "Symphony No. 94 \"Surprise\"", "artist": "Joseph Haydn", "year": 1792},
    ],
    "classical_music_romantic_period_1820_1910": [
        {"title": "Swan Lake: Theme", "artist": "Pyotr Ilyich Tchaikovsky", "year": 1876},
        {"title": "Nocturne in E♭ Major, Op. 9 No. 2", "artist": "Frédéric Chopin", "year": 1832},
        {"title": "Also sprach Zarathustra: Introduction", "artist": "Richard Strauss", "year": 1896},
    ],
    "power_ballads": [
        {"title": "I Want to Know What Love Is", "artist": "Foreigner", "year": 1984},
        {"title": "Every Rose Has Its Thorn", "artist": "Poison", "year": 1988},
        {"title": "Alone", "artist": "Heart", "year": 1987},
    ],
    "motown_magic": [
        {"title": "My Girl", "artist": "The Temptations", "year": 1964},
        {"title": "I Heard It Through the Grapevine", "artist": "Marvin Gaye", "year": 1968},
        {"title": "Stop! In The Name Of Love", "artist": "The Supremes", "year": 1965},
    ],
    "disco_favorites": [
        {"title": "Stayin' Alive", "artist": "Bee Gees", "year": 1977},
        {"title": "Le Freak", "artist": "CHIC", "year": 1978},
        {"title": "I Will Survive", "artist": "Gloria Gaynor", "year": 1978},
    ],
    "one_hit_wonders": [
        {"title": "Tainted Love", "artist": "Soft Cell", "year": 1981},
        {"title": "Come on Eileen", "artist": "Dexys Midnight Runners", "year": 1982},
        {"title": "Spirit in the Sky", "artist": "Norman Greenbaum", "year": 1969},
    ],
    "stage_screen_broadway_classics": [
        {"title": "Seasons of Love", "artist": "Original Broadway Cast of RENT", "year": 1996},
        {"title": "Defying Gravity", "artist": "Idina Menzel & Kristin Chenoweth", "year": 2003},
        {"title": "Memory", "artist": "Elaine Paige", "year": 1981},
    ],
    "stage_screen_movie_themes": [
        {"title": "My Heart Will Go On", "artist": "Céline Dion", "year": 1997},
        {"title": "Theme from Jurassic Park", "artist": "John Williams", "year": 1993},
        {"title": "Eye of the Tiger", "artist": "Survivor", "year": 1982},
    ],
    "dance_floor_anthems": [
        {"title": "Billie Jean", "artist": "Michael Jackson", "year": 1982},
        {"title": "One More Time", "artist": "Daft Punk", "year": 2000},
        {"title": "Hung Up", "artist": "Madonna", "year": 2005},
    ],
    "protest_social_justice": [
        {"title": "A Change Is Gonna Come", "artist": "Sam Cooke", "year": 1964},
        {"title": "Blowin' in the Wind", "artist": "Bob Dylan", "year": 1963},
        {"title": "Fight the Power", "artist": "Public Enemy", "year": 1989},
    ],
    "latin_crossovers": [
        {"title": "Despacito", "artist": "Luis Fonsi & Daddy Yankee", "year": 2017},
        {"title": "La Bamba", "artist": "Ritchie Valens", "year": 1958},
        {"title": "Bailando", "artist": "Enrique Iglesias", "year": 2014},
    ],
    "holiday_favorites": [
        {"title": "All I Want for Christmas Is You", "artist": "Mariah Carey", "year": 1994},
        {"title": "The Christmas Song", "artist": "Nat King Cole", "year": 1946},
        {"title": "Last Christmas", "artist": "Wham!", "year": 1984},
    ],
    "novelty_songs": [
        {"title": "Monster Mash", "artist": "Bobby \"Boris\" Pickett", "year": 1962},
        {"title": "The Streak", "artist": "Ray Stevens", "year": 1974},
        {"title": "Grandma Got Run Over by a Reindeer", "artist": "Elmo & Patsy", "year": 1979},
    ],
    "video_game_themes": [
        {"title": "Super Mario Bros. Theme", "artist": "Koji Kondo", "year": 1985},
        {"title": "Halo Theme", "artist": "Martin O'Donnell & Michael Salvatori", "year": 2001},
        {"title": "Zelda Main Theme", "artist": "Koji Kondo", "year": 1986},
    ],
    "country_duets": [
        {"title": "Islands in the Stream", "artist": "Kenny Rogers & Dolly Parton", "year": 1983},
        {"title": "Whiskey Lullaby", "artist": "Brad Paisley & Alison Krauss", "year": 2004},
        {"title": "Golden Ring", "artist": "George Jones & Tammy Wynette", "year": 1976},
    ],
    "pop_duets": [
        {"title": "Endless Love", "artist": "Diana Ross & Lionel Richie", "year": 1981},
        {"title": "Shallow", "artist": "Lady Gaga & Bradley Cooper", "year": 2018},
        {"title": "Empire State of Mind (Part II) [Duet Edit]", "artist": "Alicia Keys & Jay-Z", "year": 2009},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Normalization helpers
# ─────────────────────────────────────────────────────────────────────────────

def _try_parse_json_array(text: str) -> List[Dict]:
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _normalize_items(raw: Any) -> List[Dict[str, Any]]:
    """
    Accept a variety of shapes from XAI/test and normalize to a list of dicts
    with keys: title, artist, year (int|None).
    Also accepts alternate keys: track, track_name, artistName, yearReleased, etc.
    """
    if isinstance(raw, str):
        arr = _try_parse_json_array(raw)
        if not arr:
            return []
        raw = arr

    if isinstance(raw, dict):
        if "tracks" in raw and isinstance(raw["tracks"], list):
            raw = raw["tracks"]
        else:
            return []

    if not isinstance(raw, list):
        return []

    def pick(*keys, src: Dict[str, Any], default: Optional[str] = "") -> str:
        for k in keys:
            v = src.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return default or ""

    out: List[Dict[str, Any]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue

        title = pick("title", "track", "track_name", "trackTitle", src=it)
        artist = pick("artist", "artistName", "artist_name", src=it)
        year = it.get("year", it.get("yearReleased", it.get("year_released")))
        try:
            year = int(year) if year is not None else None
        except Exception:
            year = None

        if title and artist:
            out.append({"title": title, "artist": artist, "year": year})

    return out

def _dedupe_title_artist(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for it in items:
        key = (it["title"].lower(), it["artist"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# XAI call wrapper
# ─────────────────────────────────────────────────────────────────────────────

def call_xai(prompt: str, max_items: int, *, test_file_number: int = 0) -> List[Dict]:
    """
    Uses your xai_api_client.fetch_xai_tracks() which:
      - Calls the real XAI API when configured
      - Or returns test JSON if test_file_number>0
      - Or falls back to test files on error (if enabled in config)
    Returns a normalized list[dict].
    """
    try:
        raw = fetch_xai_tracks(prompt, test_file_number=test_file_number)
        items = _normalize_items(raw)
        items = _dedupe_title_artist(items)
        if len(items) > max_items:
            items = items[:max_items]
        logger.info("call_xai: got %d item(s) from xai/test", len(items))
        return items
    except Exception as e:
        logger.exception("call_xai failed: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def curate_tracks_via_xai(
    theme: str,
    max_items: int = 45,
    *,
    _lang: Optional[str] = None,           # reserved for future localization cues
    test_file_number: int = 0,
    assign_rank: bool = False,             # optionally add "ranking": 1..N
) -> List[Dict]:
    """
    Curate tracks for a named theme (display name or slug).
    Returns a list of dicts: {title, artist, year[, ranking?]}.

    Backward compatible with your previous signature/behavior.
    """
    slug, display_name = _resolve_theme_name_or_slug(theme)
    prompt_template = PROMPTS.get(slug, DEFAULT_PROMPT)
    prompt = prompt_template.format(max_items=max_items, display_name=display_name)

    items = call_xai(prompt, max_items=max_items, test_file_number=test_file_number)
    source = "xai/test"

    if not items:
        seeds = SEEDS_BY_SLUG.get(slug, [])
        items = seeds[:max_items]
        source = "seed"

    if assign_rank:
        for i, it in enumerate(items, start=1):
            it["ranking"] = i

    logger.info(
        "curate_tracks_via_xai slug=%s display=%r source=%s returned=%d",
        slug, display_name, source, len(items)
    )
    return items

def list_available_themes() -> List[str]:
    """Return stable slugs for discovery/UI lists."""
    return sorted(THEMES.keys())

def describe_theme(theme: str) -> Dict[str, Any]:
    """Return resolved slug, display name, and whether custom prompt/seeds exist."""
    slug, display_name = _resolve_theme_name_or_slug(theme)
    return {
        "slug": slug,
        "display_name": display_name,
        "has_prompt": slug in PROMPTS,
        "has_seeds": slug in SEEDS_BY_SLUG,
    }
