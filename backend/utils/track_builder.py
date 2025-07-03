from backend.utils.mode_utils import ModeFlag
from backend.utils.json_helpers import parse_featured_artists, normalize_name

import logging

logger = logging.getLogger(__name__)

from backend.utils.logger_factory import get_step_logger

logger_step4a = get_step_logger("STEP_4.A")
logger_step4b = get_step_logger("STEP_4.B")
logger_step4c = get_step_logger("STEP_4.C")
logger_step4d = get_step_logger("STEP_4.D")
logger_step4e = get_step_logger("STEP_4.E")

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
    print("🐛 ENTERED build_track_entry")

    logger_step4b.debug(f"🔧 [STEP_4.B] Starting build_track_entry for Rank {base.get('rank')}")
    logger_step4b.debug(f"🐛 Logger: {logger_step4b.name}, Level: {logger_step4b.getEffectiveLevel()}")
    logger_step4b.debug(f"🎼 Track: '{base.get('track_name')}', Artist: '{base.get('artist_name')}'")
    logger_step4b.debug(f"📆 Spotify data: {spotify_data}")

    if not base.get("artist_name"):
        raise ValueError(f"❌ Missing 'artist_name' in base: {base}")
    if not base.get("track_name"):
        raise ValueError(f"❌ Missing 'track_name' in base: {base}")
    if not base.get("year_released"):
        raise ValueError(f"❌ Missing 'year_released' in base: {base}")

    artist_name_raw = base["artist_name"]
    track_name_raw = base["track_name"]
    year_released = base["year_released"]

    artist_name_clean, featured_artist_name, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    featured_artist = normalize_name(featured_artist_name) if featured_artist_name else None
    track_name_clean = normalize_name(track_name_raw)
    track_display_name = track_name_clean

    mode_flag_str = base.get("mode_flag", "unknown")
    try:
        mode_flag = ModeFlag(mode_flag_str)
    except ValueError:
        logger_step4b.warning(f"⚠️ Invalid mode_flag '{mode_flag_str}' — defaulting to 'unknown'")
        mode_flag = ModeFlag.UNKNOWN

    logger_step4b.debug(f"🧽 Normalized: '{track_name_clean}' by '{artist_name_clean}', Mode: {mode_flag.value}")
    logger_step4b.debug(f"🎨 Display Name: {track_display_name}, Featured: {featured_artist}")

    result = {
        "rank": base.get("rank"),
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "artist_display_name": artist_name_raw,
        "featured_artist": featured_artist,
        "featured_artist_id": spotify_data.get("featured_artist_id"),
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotify_track_id": spotify_data.get("spotify_track_id"),
        "spotify_artist_id": spotify_data.get("artist_id") or base.get("artist_id") or f"test_{normalize_name(artist_name_raw)}",
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

    logger_step4b.debug(
        f"✅ [STEP_4.B] Track entry complete for Rank {base.get('rank')}: {result['track_name']} by {result['artist_name']}"
    )

    return result

def build_final_json(enriched_tracks, request, now, is_test_mode=False):
    seen_artists = {}
    artists = []
    tracks = []
    rankings = []

    for base in enriched_tracks:
        logger_step4a.debug("⟳ [STEP_4.A] Normalizing keys...")
        base = normalize_keys(base)

        if is_test_mode:
            spotify_data = {}
            logger_step4a.debug(f"[TEST MODE] Skipping spotify_data for: {base['track_name']} by {base['artist_name']}")
        else:
            spotify_data = base.get("spotify_data", {})
            if spotify_data:
                logger_step4a.debug(f"🎷 Enrich OK: '{base.get('track_name')}' by '{base.get('artist_name')}'")
            else:
                logger_step4a.warning(f"⚠️ Missing spotify_data for '{base.get('track_name')}'")

        track_entry = build_track_entry(base, request, spotify_data, now, is_test_mode)
        tracks.append(track_entry)

        logger_step4c.debug(f"➕ [STEP_4.C] Adding ranking for {track_entry.get('track_name')}")
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

        artist_id = track_entry.get("spotify_artist_id")
        artist_name = track_entry.get("artist_name", "unknown")
        if artist_id and artist_id not in seen_artists:
            seen_artists[artist_id] = artist_name
            logger_step4d.debug(f"🎤 [STEP_4.D] Adding artist: {artist_name} ({artist_id})")
            artists.append({
                "artist_name": artist_name,
                "spotify_artist_id": artist_id,
                "artist_artwork": spotify_data.get("artist_artwork"),
                "artist_description": base.get("artist_description"),
                "artist_mp3_url": None,
                "not_on_spotify": False
            })

    logger_step4e.info("🧱 [STEP_4.E] Assembling final JSON...")
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

    logger_step4e.info(
        f"🌟 [STEP_4.E] JSON build complete: {len(tracks)} tracks, {len(artists)} unique artists, {len(rankings)} rankings."
    )

    return final_json, tracks, artists
