# backend/services/curate.py
from __future__ import annotations
import json

# ... keep your PROMPTS and ALIASES and _resolve_theme exactly as we set them ...
# at top of curate.py
from typing import List, Dict, Optional, TypedDict

class SeedTrack(TypedDict):
    title: str
    artist: str
    year: Optional[int]

PROMPTS: dict[str, str] = {}  # replace with the full 16-prompt dict we wrote
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

def call_xai(prompt: str, max_items: int) -> List[Dict]:
    """
    Replace the try/except body with your real XAI client call.
    The function must return a JSON-serializable list of dicts.
    """
    try:
        # Example shapes you might already have in your codebase:
        # from backend.services.xai_client import chat_text
        # raw_text = chat_text(system="You are a music curator.",
        #                      user=prompt + f"\nReturn ONLY a JSON array, up to {max_items} items.")
        # return _try_parse_json_array(raw_text)[:max_items]
        return []
    except Exception:
        return []

def curate_tracks_via_xai(theme: str, max_items: int = 45, *, _lang: Optional[str] = None) -> List[Dict]:
    theme = _resolve_theme(theme)
    prompt = PROMPTS.get(theme)
    if not prompt:
        prompt = f"""
Curate {max_items} definitive tracks for the theme "{theme}".
Avoid karaoke, instrumental, tribute versions. Return JSON array: {{ "title", "artist", "year" }}.
"""
    raw = call_xai(prompt, max_items=max_items)

    # Fallback to seeds if XAI returns nothing (helps you test end-to-end today)
    if not raw and theme in SEEDS:
        raw = SEEDS[theme][:max_items]

    out: List[Dict] = []
    for it in raw[:max_items]:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()
        artist = (it.get("artist") or "").strip()
        year = it.get("year")
        if title and artist:
            out.append({"title": title, "artist": artist, "year": year})
    return out
