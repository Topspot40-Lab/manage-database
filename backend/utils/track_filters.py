# backend/utils/track_filters.py

import logging
from backend.config import ENABLE_TRACK_DETAIL

logger = logging.getLogger(__name__)

# 🎙️ Whitelist of known duets to avoid misclassifying as groups
KNOWN_DUET_PAIRS = {
    "Ella Fitzgerald & Louis Armstrong",
    "Tony Bennett & Lady Gaga",
    "Simon & Garfunkel",
    "Johnny Cash & June Carter"
}


def analyze_artist_mode(artist_name: str) -> str:
    name = artist_name.lower()
    if "feat." in name or "ft." in name:
        return "featured"
    elif " with " in name or " and " in name:
        return "duet"
    else:
        return "solo"


def is_known_duet(artist_name: str) -> bool:
    normalized = artist_name.strip().lower().replace(" ", "")
    result = normalized in {a.lower().replace(" ", "") for a in KNOWN_DUET_PAIRS}
    logger.debug(f"[STEP_1.B] is_known_duet('{artist_name}') → {result}")
    return result


def is_modern_artist(artist_name: str) -> bool:
    known_modern = {
        "Zooey Deschanel",
        "She & Him",
        "Michael Bublé",
        "Bruno Mars",
        "Postmodern Jukebox",
        "Leon Bridges",
        "Meghan Trainor",
        "Lake Street Dive"
    }
    result = artist_name.strip().lower() in {a.lower() for a in known_modern}
    logger.debug(f"[STEP_1.B] is_modern_artist('{artist_name}') → {result}")
    if result:
        logger.debug(f"[STEP_1.B] Rejected modern artist: '{artist_name}'")
    return result


def is_fake_mashup(track_name: str, artist_name: str) -> bool:
    title = track_name.lower()
    artist = artist_name.lower()

    known_bad = [
        ("sugar", "town", "four tops"),
        ("bohemian rhapsody", "", "beach boys"),
        ("satisfaction", "", "the monkees"),
        ("poker face", "", "abba"),
        ("thriller", "", "marvin gaye"),
        ("hello", "", "the supremes"),
        ("stay", "zedd", "otis redding"),
        ("driver's license", "", "carpenters"),
        ("barbie", "", "diana ross"),
    ]

    for part1, part2, bad_artist in known_bad:
        if part1 in title and bad_artist in artist:
            if not part2 or part2 in title:
                logger.debug(f"[STEP_1.B] Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
                return True

    logger.debug(f"[STEP_1.B] is_fake_mashup('{track_name}', '{artist_name}') → False")
    return False


def classify_artist_type(artist_name: str, genre: str) -> str:
    name = artist_name.lower()

    if is_known_duet(artist_name):
        classification = "DUET"
    elif " with " in name:
        classification = "DUET"
    elif " feat." in name or " featuring " in name:
        classification = "FEATURED"
    else:
        classification = "SOLO"

    logger.debug(f"[STEP_1.B] classify_artist_type('{artist_name}', '{genre}') → {classification}")
    return classification


def is_bad_track(track: dict) -> bool:
    artist = (track.get("artistName") or track.get("artist_name") or "").strip()
    title = (track.get("trackName") or track.get("track_name") or "").strip()

    if not artist or not title:
        logger.debug(f"[STEP_1.B] [INVALID] Missing artist or title in track: {track}")
        return True

    if ENABLE_TRACK_DETAIL and not track.get("detail"):
        logger.debug(f"[STEP_1.B] [WARN] Missing track detail: '{title}' by '{artist}' — Will enrich later.")

    if is_modern_artist(artist):
        return True

    if is_fake_mashup(title, artist):
        return True

    placeholder_titles = {"unknown", "track name", "song title"}
    title_lower = title.lower()
    if title_lower in placeholder_titles or "example" in title_lower or "placeholder" in title_lower:
        logger.debug(f"[STEP_1.B] [REJECTED] Placeholder title: '{title}'")
        return True

    logger.debug(f"[STEP_1.B] Track passed filtering: '{title}' by '{artist}'")
    return False


def validate_tracks(tracks: list) -> list:
    valid_tracks = []
    for track in tracks:
        if not is_bad_track(track):
            valid_tracks.append(track)
        else:
            logger.debug(f"[STEP_1.B] Invalid track skipped: {track}")
    logger.debug(f"[STEP_1.B] validate_tracks: {len(valid_tracks)} out of {len(tracks)} passed")
    return valid_tracks
