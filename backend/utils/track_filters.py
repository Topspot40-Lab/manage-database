import logging

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
        logging.info(f"🛑 Rejected modern artist: '{artist_name}'")
    return result


def is_fake_mashup(track_name: str, artist_name: str) -> bool:
    title = track_name.lower()
    artist = artist_name.lower()

    if "sugar" in title and "town" in title and "four tops" in artist:
        logging.info(f"🪤 Rejected mashup/fake combo: '{track_name}' by '{artist_name}'")
        return True
    return False


def is_bad_track(track: dict) -> bool:
    artist = track.get("artistName") or track.get("artist_name", "")
    title = track.get("trackName") or track.get("track_name", "")

    if not artist or not title:
        logging.warning(f"⚠️ Missing artist or title in track: {track}")
        return True
    if is_modern_artist(artist):
        return True
    if is_fake_mashup(title, artist):
        return True
    return False
