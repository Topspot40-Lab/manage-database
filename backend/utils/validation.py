import re
import logging


logger = logging.getLogger("Validation")

def is_valid_intro(
    intro: str,
    track_name: str,
    artist_name: str,
    genre: str = None,
    decade: str = None,
    rank: int = None
) -> bool:
    """
    Validates that the intro contains expected elements.
    Loosely matches track, artist, genre, and rank to handle variations.
    """
    if not intro:
        return False

    # Normalize quotes, apostrophes, etc.
    def normalize(s: str) -> str:
        return (
            s.lower()
            .replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("–", "-")
            .replace("—", "-")
            .strip()
        )

    intro_norm = normalize(intro)
    track_norm = normalize(track_name)
    artist_norm = normalize(artist_name)
    genre_norm = normalize(genre) if genre else None
    decade_norm = normalize(str(decade)) if decade else None

    missing_fields = []



    # 🔍 Match artist — allow "Eddy Arnold", "Eddy Arnold's", or "Eddy Arnolds'"
    artist_pattern = re.escape(artist_norm) + r"(?:'s|s')?"

    logger.debug(f"🔍 Intro Norm: {intro_norm}")
    logger.debug(f"🔍 Artist Norm: {artist_norm}")
    logger.debug(f"🔍 Pattern: {artist_pattern}")

    if not re.search(artist_pattern, intro_norm):
        logger.debug(f"🧪 Artist match failed — Pattern: {artist_pattern}, Intro: {intro_norm}")
        missing_fields.append("artist_name")

    # 🔍 Match track — allow inside quotes or alone
    if not re.search(re.escape(track_norm), intro_norm):
        missing_fields.append("track_name")

    if genre_norm and genre_norm not in intro_norm:
        missing_fields.append("genre")

    if decade_norm and decade_norm not in intro_norm:
        missing_fields.append("decade")

    if rank is not None:
        # Accept "number 1", "#1", "at 1", "rank 1"
        rank_patterns = [
            rf"\bnumber\s+{rank}\b",
            rf"\b#{rank}\b",
            rf"\brank\s+{rank}\b",
            rf"\bat\s+(number\s+)?{rank}\b"
        ]
        if not any(re.search(p, intro_norm) for p in rank_patterns):
            missing_fields.append("rank")

    if missing_fields:
        logger.debug(f"⚠️ Intro failed validation — missing: {missing_fields}\n→ Intro: {intro}")
        return False

    # Optional: log passing result
    logger.debug(f"✅ Rank {rank} intro passed validation.")
    return True
