from backend.utils.mode_utils import determine_mode_flag_basic, ModeFlag
from backend.services.track_generator import format_track_display_name
from backend.utils.json_helpers import parse_featured_artists, normalize_name

import logging

logger = logging.getLogger(__name__)

print(f"logger.name = {logger.name}")


print(f"Logger created: {logger.name}")  # TEMP debug
logger.debug(f"[DEBUG TEST] Logger name: {logger.name}, effective level: {logger.getEffectiveLevel()}")


def normalize_keys(base: dict) -> dict:
    """Ensure consistent snake_case keys for downstream processing."""
    return {
        "track_name": base.get("track_name") or base.get("trackName"),
        "artist_name": base.get("artist_name") or base.get("artistName"),
        "year_released": base.get("year_released") or base.get("yearReleased"),
        "rank": base.get("rank"),
        "intro": base.get("intro"),
        "detail": base.get("detail"),
        **base  # Preserve any other existing fields
    }


def build_track_entry(base, request, spotify_data, now, is_test_mode=False):

    logger.debug(f"🐛 DEBUG in build_track_entry — logger.name = {logger.name}")
    logger.debug(f"🐛 effective level = {logger.getEffectiveLevel()}")
    logger.debug("🛠️ build_track_entry called")
    logger.debug(f"🔍 Track = '{base.get('track_name')}', Artist = '{base.get('artist_name')}'")
    logger.debug(f"🔍 spotify_data for '{base.get('track_name')}' → {spotify_data}")

    if spotify_data:
        logger.debug(f"🧪 spotify_data keys = {list(spotify_data.keys())}")
    else:
        logger.debug("🧪 spotify_data is None (likely test mode)")

    artist_name_raw = base.get("artist_name")
    track_name_raw = base.get("track_name")
    year_released = base.get("year_released")

    if not artist_name_raw:
        raise ValueError(f"❌ Missing 'artist_name' in base. Debug info: {base}")
    if not track_name_raw:
        raise ValueError(f"❌ Missing 'track_name' in base. Debug info: {base}")
    if not year_released:
        raise ValueError(f"❌ Missing 'year_released' in base. Debug info: {base}")

    # Parse and normalize names
    artist_name_clean, featured_artist_name = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    featured_artist = normalize_name(featured_artist_name) if featured_artist_name else None
    track_name_clean = normalize_name(track_name_raw)

    mode_flag: ModeFlag = determine_mode_flag_basic(artist_name_raw)

    track_display_name = track_name_clean  # Keep title clean — display artist includes the extra info

    return {
        "rank": base.get("rank"),
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "artist_display_name": artist_name_raw,  # 👍 Optional new field
        "featured_artist": featured_artist,
        "featured_artist_id": spotify_data.get("featured_artist_id"),
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotify_track_id": spotify_data.get("spotify_track_id"),
        "spotify_artist_id": spotify_data.get("artist_id") or base.get(
            "artist_id") or f"test_{normalize_name(artist_name_raw)}",
        "mode_flag": mode_flag.value,
        "duration_ms": spotify_data.get("duration_ms"),
        "popularity": spotify_data.get("popularity"),
        "album_artwork": spotify_data.get("album_artwork"),
        "year_released": year_released,
        "is_explicit": False,
        "created_at": now,
        "intro": base.get("intro"),
        "detail": base.get("detail"),
        "detail_mp3_url": base.get("detail_mp3_url"),
        "not_on_spotify": spotify_data.get("not_on_spotify", False),
    }

def build_final_json(enriched_tracks, request, now, is_test_mode=False):
    """Return (final_json, track_entries, artist_entries) tuple.

    The JSON structure follows the format:
    core_tables → track_tables → ranking_tables
    """

    seen_artists = {}
    artists = []
    tracks = []
    rankings = []
    for base in enriched_tracks:
        base = normalize_keys(base)
        logger.debug(f"🐍 Normalized base keys = {list(base.keys())}")
        logger.debug(
            f"🔍 Normalized artist_name = {base.get('artist_name')} — original artistName = {base.get('artistName')}")

        if is_test_mode:
            spotify_data = {}
            logger.debug(f"[TEST MODE] Skipping spotify_data for: {base['track_name']} by {base['artist_name']}")
        else:
            spotify_data = base.get("spotify_data", {})
            if spotify_data:
                logger.debug(
                    f"🎧 Enrich OK: '{base.get('trackName')}' by '{base.get('artistName')}' — "
                    f"spotify_data keys: {list(spotify_data.keys())}"
                )
                if normalize_name(spotify_data.get("artistName", "")) != normalize_name(base.get("artistName", "")):
                    logger.warning(
                        f"⚠️ ARTIST MISMATCH: Input='{base.get('artistName')}', "
                        f"Spotify='{spotify_data.get('artistName')}' — check for alternate versions or covers."
                    )
            else:
                logger.warning(
                    f"⚠️ Missing spotify_data for '{base.get('trackName')}' by '{base.get('artistName')}' — "
                    f"falling back to raw input"
                )

        track_entry = build_track_entry(base, request, spotify_data, now, is_test_mode)
        tracks.append(track_entry)

        logger.debug(f"🧾 Final artist ID = {track_entry.get('spotify_artist_id')}")
        logger.debug(f"📦 Got track_entry keys: {list(track_entry.keys())}")
        logger.debug(f"🎧 Track ID for '{track_entry.get('track_name')}' = {track_entry.get('spotify_track_id')}")

        rankings.append({
            "track_id": track_entry.get("spotify_track_id"),
            "track_name": track_entry.get("track_name"),
            "artist_name": track_entry.get("artist_name"),
            "rank": base.get("rank"),
            "genre": request.genre,
            "decade": request.decade,
            "tracklist": "TopSpot Autogen",
            "intro": track_entry.get("intro"),
            "intro_mp3_url": track_entry.get("intro_mp3_url"),
            "ranking_date": now.split("T")[0],
        })
        artist_id = (
            track_entry.get("spotify_artist_id")
            or base.get("artist_id")  # fallback if not in track_entry
            or f"test_{normalize_name(track_entry.get('artist_name', 'unknown'))}"
        )
        artist_name = track_entry.get("artist_name", "unknown")

        logger.debug(f"🧾 Final artist ID = {artist_id}")

        if artist_id and artist_id not in seen_artists:
            seen_artists[artist_id] = artist_name
            artists.append({
                "artist_name": artist_name,
                "spotify_artist_id": artist_id,
                "artist_artwork": track_entry.get("artist_artwork"),
                "artist_description": track_entry.get("artist_description"),
                "artist_mp3_url": None,
                "not_on_spotify": False
            })



    final_json = {
        "language": request.language,
        "category": request.decade,
        "genre": request.genre,
        "generated_at": now,
        "core_tables": {
            "genre": [{"genre_name": request.genre}],
            "decade": [{"decade_name": request.decade}],
            "artist": artists
        },
        "track_tables": {
            "track": tracks,
            "tracklist": [{
                "name": "TopSpot Autogen",
                "curator": "Mr. Ed",
                "is_official": True,
                "language": request.language[:2],
                "notes": f"Generated for {request.genre} - {request.decade}",
                "created_at": now
            }]
        },
        "ranking_tables": {
            "track_ranking": rankings
        }
    }

    logger.debug(f"🎨 Artists in final JSON: {len(artists)}")

    return final_json, tracks, artists
