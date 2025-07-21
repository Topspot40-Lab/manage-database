# backend/utils/validation.py

import re
import logging
from backend.utils.json_helpers import normalize_text

logger = logging.getLogger("Validation")

def is_valid_intro(intro: str, track_name: str, artist_name: str, genre: str = None, decade: str = None, rank: int = None) -> bool:
    """
    Validates that the intro contains all the required elements.
    """
    if not intro:
        return False

    intro_norm = normalize_text(intro)
    missing_fields = []

    if normalize_text(track_name) not in intro_norm:
        missing_fields.append("track_name")
    if normalize_text(artist_name) not in intro_norm:
        missing_fields.append("artist_name")
    if genre and normalize_text(genre) not in intro_norm:
        missing_fields.append("genre")
    if decade and str(decade) not in intro_norm:
        missing_fields.append("decade")
    if rank is not None:
        if not re.search(rf"(rank|#|at)\s*{rank}\b", intro_norm):
            missing_fields.append(f"rank={rank}")

    if missing_fields:
        logger.debug(f"⚠️ Intro missing elements: {missing_fields}\n→ Intro: {intro}")
        return False

    return True
