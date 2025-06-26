from backend.utils.mode_utils import determine_mode_flag_basic, ModeFlag
from backend.services.track_generator import format_track_display_name
from backend.utils.json_helpers import parse_featured_artists, normalize_name

import logging
logger = logging.getLogger(__name__)
def build_track_entry(base, request, spotify_data, now, is_test_mode=False):
    if is_test_mode:
        artist_name_raw = base["artistName"]
        track_name_raw = base["trackName"]
        year_released = base["yearReleased"]
    else:
        artist_name_raw = base["artist_name"]
        track_name_raw = base["track_name"]
        year_released = base["year_released"]

    # Parse and normalize names
    artist_name_clean, featured_artist_name = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    featured_artist = normalize_name(featured_artist_name) if featured_artist_name else None
    track_name_clean = normalize_name(track_name_raw)

    mode_flag: ModeFlag = determine_mode_flag_basic(artist_name_raw)

    track_display_name = format_track_display_name(
        track_name_clean,
        featured_artist_name,
        mode_flag.value,
    )

    return {
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "artist_display_name": artist_name_raw,  # 👍 Optional new field
        "featured_artist": featured_artist,
        "featured_artist_id": spotify_data.get("featured_artist_id"),
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotify_track_id": spotify_data.get("spotify_track_id"),
        "spotify_artist_id": spotify_data.get("artist_id"),
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
        if is_test_mode:
            spotify_data = {}
            logger.debug(f"[TEST MODE] Skipping spotify_data for: {base.get('trackName')} by {base.get('artistName')}")
        else:
            spotify_data = base.get("spotify_data", {})

        track_entry = build_track_entry(base, request, spotify_data, now, is_test_mode)

        tracks.append(track_entry)

        rankings.append({
            "track_id": track_entry.get("spotify_track_id"),
            "rank": base.get("rank"),
            "genre": request.genre,
            "decade": request.decade,
            "created_at": now,
        })

        artist_id = track_entry.get("spotify_artist_id")
        artist_name = track_entry.get("artist_name")
        if artist_id and artist_id not in seen_artists:
            seen_artists[artist_id] = artist_name
            artists.append({
                "artist_name": artist_name,
                "spotify_artist_id": artist_id,
                "artist_artwork": spotify_data.get("artist_artwork"),
                "artist_description": spotify_data.get("artist_description"),
            })

    final_json = {
        "language": request.language,
        "category": request.decade,
        "genre": request.genre,
        "generated_at": now,
        "core_tables": {
            "artist": artists
        },
        "track_tables": {
            "track": tracks
        },
        "ranking_tables": {
            "ranking": rankings
        }
    }

    return final_json, tracks, artists