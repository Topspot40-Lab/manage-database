import logging
logger = logging.getLogger(__name__)

from backend.services.spotify_service import get_spotify_data, determine_mode_flag, format_track_display_name
from backend.utils.json_helpers import parse_featured_artists, normalize_name
from jsonschema import validate, ValidationError


def fetch_and_validate_tracks(base):
    artist_name_raw = base["artistName"]
    track_name_raw = base["trackName"]
    rank = base.get("rank", "?")  # 👈 Optional safeguard

    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    track_name_clean = normalize_name(track_name_raw)

    logger.debug(f"🎯 [Rank #{rank}] Searching Spotify with: '{track_name_clean}' by '{artist_name_clean}'")

    spotify_data = get_spotify_data(track_name_clean, artist_name_clean)
    return spotify_data


def process_artist(base, spotify_data, seen_artists, description_cache, language):
    from backend.services.xai_service import get_artist_description

    artist_name_raw = base["artistName"]
    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)

    # ✅ Only skip if we already cached a valid Spotify match
    if artist_name_clean in seen_artists:
        logger.debug(f"🛑 Skipping already-processed artist: {artist_name_clean}")
        return None

    if not spotify_data or not spotify_data.get("artist_id"):
        logger.warning(f"⚠️  Skipping '{artist_name_clean}' — no valid Spotify ID")
        return None

    if artist_name_clean not in description_cache:
        logger.debug(f"🔍 Fetching description for: {artist_name_clean}")
        desc = get_artist_description(artist_name_clean, language=language)
        if not desc:
            desc = None
        description_cache[artist_name_clean] = desc

    detail_mp3_url = (
        base.get("detail_mp3_url")
        if spotify_data.get("artist_id")
        else "tts/detail_unavailable.mp3"
    )

    artist_entry = {
        "artist_name": artist_name_clean,
        "spotify_artist_id": spotify_data["artist_id"],
        "artist_artwork": spotify_data.get("artist_artwork"),
        "artist_description": description_cache[artist_name_clean],
        "artist_mp3_url": detail_mp3_url,
        "not_on_spotify": False,
    }

    # logger.debug(f"🎨 Artist entry built: {artist_entry}")

    # ✅ Now safe to mark as processed
    seen_artists[artist_name_clean] = True
    return artist_entry

def build_track_entry(base, request, spotify_data, now):
    artist_name_raw = base["artistName"]
    track_name_raw = base["trackName"]

    # Split out main and featured/duet artist
    artist_name_clean, featured_artist_name = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    track_name_clean = normalize_name(track_name_raw)

    # Determine mode (SOLO, DUET, FEATURED, etc.)
    mode_flag, featured_artist_id = determine_mode_flag(
        artist_name_raw, spotify_data.get("artistNameCandidates", [])
    )

    # Format display name for UI/console
    track_display_name = format_track_display_name(
        track_name_clean,
        featured_artist_name,
        mode_flag.value
    )

    track_entry = {
        "rank": base.get("rank"),
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "featured_artist": featured_artist_name if featured_artist_name else None,
        "featured_artist_id": featured_artist_id,
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotify_track_id": spotify_data.get("spotify_track_id") if spotify_data else None,
        "spotify_artist_id": spotify_data.get("artist_id") if spotify_data else None,
        "mode_flag": mode_flag.value,
        "duration_ms": spotify_data.get("duration_ms") if spotify_data else None,
        "popularity": spotify_data.get("popularity") if spotify_data else None,
        "album_artwork": spotify_data.get("album_artwork") if spotify_data else None,
        "year_released": int(base["yearReleased"]),
        "is_explicit": False,
        "created_at": now,
        "detail": base.get("detail"),
        "detail_mp3_url": base.get("detail_mp3_url"),
        "not_on_spotify": not spotify_data or not spotify_data.get("spotify_track_id")
    }

    # logger.debug(f"🎵 Track entry built: {track_entry}")
    logger.debug(f"🎯 Final entry for '{track_display_name}': mode={mode_flag.name}, featured_id={featured_artist_id}")

    return track_entry
def build_ranking_entry(base, request, spotify_data, now):
    artist_name_clean = normalize_name(
        base.get("artistName") or base.get("artist_name")
    )
    track_name_clean = normalize_name(
        base.get("trackName") or base.get("track_name")
    )

    ranking_entry = {
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "spotify_track_id": spotify_data.get("spotify_track_id") if spotify_data else None,
        "genre": request.genre,
        "decade": request.decade,
        "tracklist": "TopSpot Autogen",
        "rank": base["rank"],
        "intro": base.get("intro"),
        "intro_mp3_url": base.get("intro_mp3_url"),
        "ranking_date": now[:10]
    }

    return ranking_entry

def build_final_json(enriched_tracks, request, now):
    from backend.services.spotify_service import handle_missing_track  # Ensure this is imported
    from backend.config import SCHEMA_PATH
    import json

    seen_artists = {}
    description_cache = {}
    artists = []
    tracks = []
    rankings = []
    bad_tracks = []
    spare_tracks = []  # Optional: pass spares into handle_missing_track()

    for base in enriched_tracks:
        spotify_data = fetch_and_validate_tracks(base)

        # 🧑 Main artist processing
        artist_entry = process_artist(
            base=base,
            spotify_data=spotify_data,
            seen_artists=seen_artists,
            description_cache=description_cache,
            language=request.language
        )
        if artist_entry:
            artists.append(artist_entry)

        # 🎤 Featured artist processing (if present)
        featured_artist_id = spotify_data.get("featured_artist_id") if spotify_data else None
        featured_artist_name = base.get("featured_artist") or (spotify_data.get("featured_artist_name") if spotify_data else None)

        if featured_artist_id and featured_artist_name:
            featured_name_clean = normalize_name(featured_artist_name)
            if featured_name_clean not in seen_artists:
                logger.debug(f"🎤 Adding featured artist: {featured_name_clean}")
                featured_spotify_data = get_spotify_data(base["trackName"], featured_name_clean)
                featured_artist_entry = {
                    "artist_name": featured_name_clean,
                    "spotify_artist_id": featured_artist_id,
                    "artist_artwork": featured_spotify_data.get("artist_artwork") if featured_spotify_data else None,
                    "artist_description": None,
                    "artist_mp3_url": None,
                    "not_on_spotify": False
                }
                artists.append(featured_artist_entry)
                seen_artists[featured_name_clean] = True

        # 🎵 Track + Ranking processing
        track_entry = build_track_entry(base, request, spotify_data, now)
        ranking_entry = build_ranking_entry(base, request, spotify_data, now)

        if not track_entry or not track_entry.get("spotify_track_id"):
            bad_tracks.append(track_entry)
            continue

        # Only keep as many tracks as requested
        if len(tracks) < request.num_tracks:
            tracks.append(track_entry)
            rankings.append(ranking_entry)
        else:
            spare_tracks.append(track_entry)

    # 🎯 Give the user a chance to fix bad tracks
    for bad_track in bad_tracks:
        try:
            success = handle_missing_track(bad_track, tracks, spare_tracks)
            if success:
                spotify_data = {
                    "spotify_track_id": bad_track.get("spotify_track_id"),
                    "album_artwork": bad_track.get("album_artwork"),
                    "artist_id": bad_track.get("artist_id"),
                    "artist_artwork": bad_track.get("artist_artwork"),
                    "duration_ms": bad_track.get("duration_ms"),
                    "popularity": bad_track.get("popularity"),
                    "featured_artist_id": bad_track.get("featured_artist_id"),
                    "featured_artist_name": bad_track.get("featured_artist"),
                }
                ranking_entry = build_ranking_entry(bad_track, request, spotify_data, now)
                rankings.append(ranking_entry)
                logger.debug(f"📊 Added ranking entry for recovered track: #{bad_track.get('rank')} — {bad_track.get('trackName')}")
        except Exception as e:
            logger.warning(f"⚠️ Error handling missing track: {e}")


    if spare_tracks:
        logger.info(f"🪙 {len(spare_tracks)} spare tracks available.")
    else:
        logger.warning("🚨 No spare tracks available after filtering.")

    # 🧱 Build final structure after fixes
    final_json = {
        "core_tables": {
            "genre": [{"genre_name": request.genre}],
            "decade": [{"decade_name": request.decade}],
            "artist": artists
        },
        "track_tables": {
            "track": tracks,
            "tracklist": [
                {
                    "name": "TopSpot Autogen",
                    "curator": "Mr. Ed",
                    "is_official": True,
                    "language": request.language[:2].lower(),
                    "notes": f"Generated for {request.decade} - {request.genre}",
                    "created_at": now
                }
            ]
        },
        "ranking_tables": {
            "track_ranking": rankings
        }
    }

    # ✅ Schema validation (after cleanup)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
        validate(instance=final_json, schema=schema)
        logger.info("✅ JSON schema validation passed.")
    except ValidationError as e:
        logger.error(f"❌ JSON schema validation failed: {e.message}")
        raise
    except Exception as e:
        logger.warning(f"⚠️ Could not validate against schema: {e}")

    logger.debug("🔍 JSON Preview (keys only):")
    for key in final_json:
        logger.debug(f"  🔹 {key}: {list(final_json[key].keys())}")

    logger.info(f"📦 Final JSON built with {len(tracks)} tracks and {len(artists)} artists.")

    logger.info(f"🧾 Track Summary:")
    logger.info(f"   - Tracks Requested: {request.num_tracks}")
    logger.info(f"   - Final Tracks Included: {len(tracks)}")
    logger.info(f"   - Spare Tracks Remaining: {len(spare_tracks)}")
    logger.info(f"   - Tracks Replaced or Skipped: {len(bad_tracks)}")

    return final_json, tracks, artists

