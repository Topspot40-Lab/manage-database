# backend/utils/tts_paths.py
from backend.utils.naming import slug_underscore

# Single source of truth for the filename
INTRO_NAME_FMT = "intro_{rank:02d}_{track_id}.mp3"

def intro_mp3_key(category: str, genre: str, lang_code: str, track_id: str, rank: int) -> str:
    """
    Builds the *same* object key used for TrackRanking intros,
    e.g.: before_1990s/latin_favorites/es/intro_01_2aEe...fs.mp3
    """
    d = slug_underscore(category)
    g = slug_underscore(genre)
    lc = (lang_code or "en").lower()
    return f"{d}/{g}/{lc}/{INTRO_NAME_FMT.format(rank=rank, track_id=track_id)}"
