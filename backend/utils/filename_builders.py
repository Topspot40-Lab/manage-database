import re

def normalize_for_filename(text: str) -> str:
    # identical to your existing one (keep only one copy in the codebase)
    return re.sub(r"\W", "", (text or "").lower().replace(" ", "_").replace("-", "_"))

def build_intro_filename(decade: str, genre: str, rank: int) -> str:
    """
    Canonical intro MP3 filename used across the app.
    Pattern: {decade}_{genre}_{rank:02}.mp3  (normalized)
    """
    d = normalize_for_filename(decade or "unknown")
    g = normalize_for_filename(genre or "unknown")
    return f"{d}_{g}_{int(rank):02}.mp3"
