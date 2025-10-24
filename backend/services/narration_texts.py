# backend/services/narration_texts.py
from __future__ import annotations
from typing import Optional
def assemble_narration_texts(
    *,
    track: Optional[object] = None,
    artist: Optional[object] = None,
    collection_intro: Optional[str] = None,
    mode: str = "decade_genre"
) -> dict:
    if mode == "collection":
        intro_text = (collection_intro or
                      getattr(track, "intro", "") or
                      getattr(track, "info", "") or "")
    else:
        intro_text = (getattr(track, "intro", "") or
                      getattr(track, "info", "") or "")

    # 🔧 include detail_text alias
    detail_text = (getattr(track, "detail_text", "") or
                   getattr(track, "track_detail", "") or
                   getattr(track, "detail", "") or "")

    artist_text = (getattr(artist, "artist_description", "") or
                   getattr(artist, "description", "") or "")

    return {
        "intro_text": intro_text.strip(),
        "detail_text": detail_text.strip(),
        "artist_text": artist_text.strip(),
    }
