from __future__ import annotations
from typing import List, Dict, Any, Optional

from backend.services.xai_track_descriptions import get_track_descriptions_from_xai

def fill_intro_detail_for_any_context(
    tracks: List[Dict[str, Any]],
    *,
    language: str = "en",
    decade: Optional[str] = None,
    genre: Optional[str] = None,
    theme_slug: Optional[str] = None,
    theme_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Unifies both worlds:
      - decade/genre flow → pass decade, genre
      - collections flow  → pass theme_slug/theme_name

    We adapt to the existing signature:
      get_track_descriptions_from_xai(track_data, language, category, genre)

    Mapping:
      category := decade or theme_name or theme_slug or "Collection"
      genre    := genre  or "Mixed"
    """
    category = (decade or theme_name or theme_slug or "Collection").strip()
    genre_   = (genre or "Mixed").strip()

    # Reuse your existing batcher (keeps camelCase fields intact)
    payload = get_track_descriptions_from_xai(
        track_data=tracks,          # can be list; the helper supports list or {"tracks":[...]}
        language=language,
        category=category,
        genre=genre_
    )
    # payload shape: {"language", "category", "genre", "tracks": [...]}
    # The helper already merges "intro"/"detail" back into each track dict.
    return payload["tracks"]
