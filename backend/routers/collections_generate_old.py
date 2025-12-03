from __future__ import annotations
from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any
from backend.services.curate import curate_tracks_via_xai  # uses your seeds/XAI

router = APIRouter(prefix="/collections", tags=["Collections (Generate JSON)"])

SLUG_TO_NAME = {
    "power_ballads": "Power Ballads",
    "disney_classics_pre_1988": "Disney: Classics (pre-1988)",
    "disney_revival_after_1988": "Disney: Revival (after-1988)",
    "motown_magic": "Motown Magic",
    "disco_favorites": "Disco Favorites",
    "one_hit_wonders": "One-Hit Wonders",
    "dance_floor_anthems": "Dance Floor Anthems",
    "latin_crossovers": "Latin Crossovers",
    "novelty_songs": "Novelty Songs",
    "holiday_favorites": "Holiday Favorites",
    "protest_social_justice": "Protest & Social Justice",
    "stage_screen_broadway_classics": "Stage & Screen: Broadway Classics",
    "stage_screen_movie_themes": "Stage & Screen: Movie Themes",
    "classical_music_baroque_period_1600_1750": "Classical Music: Baroque Period (1600-1750)",
    "classical_music_classical_period_1750_1820": "Classical Music: Classical Period (1750-1820)",
    "classical_music_romantic_period_1820_1910": "Classical Music: Romantic Period (1820-1910)",
}

def _theme_from_slug(slug: str) -> str:
    return SLUG_TO_NAME.get(slug, slug.replace("_", " ").title())

def _first(d: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v if not isinstance(v, str) else v.strip()
    return default

def _parse_year(v: Any) -> int | None:
    try:
        y = int(str(v)[:4])
        return y if 1600 <= y <= 2100 else None
    except Exception:
        return None

@router.get("/{slug}/generate-json")
def generate_json_for_collection(
    slug: str,
    target_count: int = Query(45, ge=1, le=100),
):
    try:
        theme = _theme_from_slug(slug)

        # Seeds/XAI
        candidates: List[Dict[str, Any]] = curate_tracks_via_xai(theme, max_items=target_count) or []

        tracks: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()  # de-dupe by (title, artist)

        # Iterate all candidates, stop when we hit target_count AFTER filtering/deduping
        for c in candidates:
            if not isinstance(c, dict):
                continue

            title = _first(c, "title", "trackName", "track", "name")
            artist = _first(c, "artist", "artistName")
            year = _parse_year(_first(c, "year", "yearReleased"))

            if not title or not artist:
                continue

            key = (title.lower(), artist.lower())
            if key in seen:
                continue
            seen.add(key)

            tracks.append({
                "ranking": len(tracks) + 1,
                "title": title,
                "artistName": artist,
                "year": year,
                "spotifyTrackId": None,
                "albumName": None,
                "albumArtUrl": None,
            })

            if len(tracks) >= target_count:
                break

        return {
            "collection": {"name": theme, "slug": slug, "type": "SPECIALTY"},
            "tracks": tracks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"curator failed: {type(e).__name__}: {e}")
