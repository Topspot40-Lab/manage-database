# backend/services/curate.py
from __future__ import annotations
import json
import logging
from typing import List, Dict, Optional, TypedDict, Any

from backend.services.xai_api_client import fetch_xai_tracks  # ✅ use your client

logger = logging.getLogger("curate")

class SeedTrack(TypedDict):
    title: str
    artist: str
    year: Optional[int]

PROMPTS: dict[str, str] = {}  # fill with your 16 prompts when ready
ALIASES: dict[str, str] = {"Protest & Social Anthems": "Protest & Social Justice"}

def _resolve_theme(theme: str) -> str:
    return ALIASES.get(theme, theme)

SEEDS: Dict[str, List[SeedTrack]] = {
    "Disney: Classics (pre-1988)": [
        {"title": "When You Wish Upon a Star", "artist": "Cliff Edwards", "year": 1940},
        {"title": "A Dream Is a Wish Your Heart Makes", "artist": "Ilene Woods", "year": 1950},
        {"title": "Heigh-Ho", "artist": "The Dwarf Chorus", "year": 1937},
    ],
    "Power Ballads": [
        {"title": "I Want to Know What Love Is", "artist": "Foreigner", "year": 1984},
        {"title": "Every Rose Has Its Thorn", "artist": "Poison", "year": 1988},
        {"title": "Alone", "artist": "Heart", "year": 1987},
    ],
    "Motown Magic": [
        {"title": "My Girl", "artist": "The Temptations", "year": 1964},
        {"title": "I Heard It Through the Grapevine", "artist": "Marvin Gaye", "year": 1968},
        {"title": "Stop! In The Name Of Love", "artist": "The Supremes", "year": 1965},
    ],
}

def _try_parse_json_array(text: str) -> List[Dict]:
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _normalize_items(raw: Any) -> List[Dict[str, Any]]:
    """
    Accept a variety of shapes from XAI/test and normalize to a list of dicts
    with keys: title, artist, year.
    """
    if isinstance(raw, str):
        # Maybe they returned a JSON array as a string
        arr = _try_parse_json_array(raw)
        if not arr:
            return []
        raw = arr

    if isinstance(raw, dict):
        # Allow {"tracks": [...]}
        if "tracks" in raw and isinstance(raw["tracks"], list):
            raw = raw["tracks"]
        else:
            return []

    if not isinstance(raw, list):
        return []

    out: List[Dict[str, Any]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()
        artist = (it.get("artist") or "").strip()
        year = it.get("year")
        if title and artist:
            out.append({"title": title, "artist": artist, "year": year})
    return out

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
        logger.info("call_xai: got %d item(s) from xai/test", len(items))
        return items[:max_items]
    except Exception as e:
        logger.exception("call_xai failed: %s", e)
        return []

def curate_tracks_via_xai(theme: str, max_items: int = 45, *, _lang: Optional[str] = None, test_file_number: int = 0) -> List[Dict]:
    theme = _resolve_theme(theme)
    prompt = PROMPTS.get(theme) or (
        f'Curate {max_items} definitive tracks for the theme "{theme}". '
        f'Avoid karaoke/tribute/instrumental versions. '
        f'Return ONLY a JSON array of objects with keys: "title", "artist", "year".'
    )

    raw = call_xai(prompt, max_items=max_items, test_file_number=test_file_number)
    source = "xai/test"

    # Fallback to seeds if nothing came back
    if not raw and theme in SEEDS:
        raw = SEEDS[theme][:max_items]
        source = "seed"

    logger.info("curate_tracks_via_xai theme=%r source=%s returned=%d", theme, source, len(raw))
    return raw
