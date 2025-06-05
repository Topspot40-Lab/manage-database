import logging

# 🧠 Check if the artist is modern and should be excluded (even if they sound retro)
def is_modern_artist(artist_name: str) -> bool:
    # Set of known modern artists often mistaken for retro performers
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

    # Normalize input name and compare to known moderns (case-insensitive)
    result = artist_name.strip().lower() in {a.lower() for a in known_modern}
    if result:
        logging.info(f"🛑 Rejected modern artist: '{artist_name}'")
    return result


# 🧪 Detect if the track is a known fake, remix, or hallucinated combo
def is_fake_mashup(track_name: str, artist_name: str) -> bool:
    title = track_name.lower()
    artist = artist_name.lower()

    # Specific known bad combo from previous XAI output
    if "sugar" in title and "town" in title and "four tops" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True

    # Known bad combos we've seen or might reasonably expect
    if "bohemian rhapsody" in title and "beach boys" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "satisfaction" in title and "the monkees" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "poker face" in title and "abba" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "thriller" in title and "marvin gaye" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "hello" in title and "the supremes" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "stay" in title and "otis redding" in artist and "zedd" in title:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "driver's license" in title and "carpenters" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    if "barbie" in title and "diana ross" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True


    return False


# ✅ Master filter: Exclude tracks that are empty, modern imposters, or fake mashups
def is_bad_track(track: dict) -> bool:
    # Normalize key names (trackName vs. track_name) for flexibility
    artist = track.get("artistName") or track.get("artist_name", "")
    title = track.get("trackName") or track.get("track_name", "")

    # Filter 1: Missing required fields
    if not artist or not title:
        logging.warning(f"⚠️ Missing artist or title in track: {track}")
        return True

    # Filter 2: Known modern artist (e.g., retro-sounding but disqualified)
    if is_modern_artist(artist):
        return True

    # Filter 3: Known mashups or fake track combinations
    if is_fake_mashup(title, artist):
        return True

    # Filter 4: Placeholder or generic names
    placeholder_titles = {"unknown", "track name", "song title"}
    title_lower = title.strip().lower()
    if title_lower in placeholder_titles or "example" in title_lower or "placeholder" in title_lower:
        logging.warning(f"⚠️ Rejected placeholder title: '{title}'")
        return True


    # ✅ Passed all filters
    return False

# ✅ Validates an entire track list (assumes each entry is a dict)
def validate_tracks(tracks: list) -> list:
    valid_tracks = []
    for track in tracks:
        if not is_bad_track(track):
            valid_tracks.append(track)
        else:
            logging.warning(f"⛔ Invalid track skipped: {track}")
    return valid_tracks
