import logging

logger = logging.getLogger(__name__)


# 🎙️ Whitelist of known duets to avoid misclassifying as groups
KNOWN_DUET_PAIRS = {
    "Ella Fitzgerald & Louis Armstrong",
    "Tony Bennett & Lady Gaga",
    "Simon & Garfunkel",
    "Johnny Cash & June Carter"
}

def is_known_duet(artist_name: str) -> bool:
    normalized = artist_name.strip().lower().replace(" ", "")
    return normalized in {a.lower().replace(" ", "") for a in KNOWN_DUET_PAIRS}


# 🧠 Check if the artist is modern and should be excluded (even if they sound retro)
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
    if result:
        logging.info(f" Rejected modern artist: '{artist_name}'")
    return result


# 🧪 Detect if the track is a known fake, remix, or hallucinated combo
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
        if part1 in title and part2 in title and bad_artist in artist:
            logging.info(f" Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
            return True
    return False


# 🎯 Classify artist collaboration type based on formatting and genre context
def classify_artist_type(artist_name: str, genre: str) -> str:
    name = artist_name.lower()

    if is_known_duet(artist_name):
        return "DUET"
    if " with " in name:
        return "DUET"
    if " feat." in name or " featuring " in name:
        return "FEATURED"

    return "SOLO"


# ✅ Master filter: Exclude tracks that are empty, modern imposters, or fake mashups
from backend.config import ENABLE_TRACK_DESCRIPTION
import logging

def is_bad_track(track: dict) -> bool:
    artist = track.get("artistName") or track.get("artist_name", "")
    title = track.get("trackName") or track.get("track_name", "")

    # Check for required fields
    if not artist or not title:
        logging.warning(f"[INVALID] Missing artist or title in track: {track}")
        return True

    # Warn if description is missing — don't reject
    if ENABLE_TRACK_DESCRIPTION and not track.get("detail"):
        logging.warning(f"[WARN] Missing track description: '{title}' by '{artist}' — Will enrich later.")

    # Block modern artists
    if is_modern_artist(artist):
        return True

    # Block known hallucinated/fake combos
    if is_fake_mashup(title, artist):
        return True

    # Block obvious placeholders
    placeholder_titles = {"unknown", "track name", "song title"}
    title_lower = title.strip().lower()
    if title_lower in placeholder_titles or "example" in title_lower or "placeholder" in title_lower:
        logging.warning(f"[REJECTED] Placeholder title: '{title}'")
        return True

    return False



# ✅ Validates an entire track list (assumes each entry is a dict)
def validate_tracks(tracks: list) -> list:
    valid_tracks = []
    for track in tracks:
        if not is_bad_track(track):
            valid_tracks.append(track)
        else:
            logging.warning(f" Invalid track skipped: {track}")
    return valid_tracks
