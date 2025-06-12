import logging
from backend.services.spotify_service import get_spotify_data, determine_mode_flag, format_track_display_name
from backend.utils.json_helpers import parse_featured_artists, normalize_name


def fetch_and_validate_tracks(base):
    artist_name_raw = base["artistName"]
    track_name_raw = base["trackName"]

    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    track_name_clean = normalize_name(track_name_raw)

    logging.info(f"🎯 Searching Spotify with: '{track_name_clean}' by '{artist_name_clean}'")

    spotify_data = get_spotify_data(track_name_clean, artist_name_clean)
    logging.debug(f"✅ Spotify data received: {spotify_data}")
    return spotify_data

def process_artist(base, spotify_data, seen_artists, description_cache, language):
    from backend.services.xai_service import get_artist_description

    artist_name_raw = base["artistName"]
    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)

    # ✅ Only skip if we already cached a valid Spotify match
    if artist_name_clean in seen_artists:
        logging.info(f"🛑 Skipping already-processed artist: {artist_name_clean}")
        return None

    if not spotify_data or not spotify_data.get("artist_id"):
        logging.warning(f"⚠️  Skipping '{artist_name_clean}' — no valid Spotify ID")
        return None

    if artist_name_clean not in description_cache:
        logging.info(f"🔍 Fetching description for: {artist_name_clean}")
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

    logging.debug(f"🎨 Artist entry built: {artist_entry}")

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

    logging.debug(f"🎵 Track entry built: {track_entry}")
    logging.debug(f"🎯 Final entry for '{track_display_name}': mode={mode_flag.name}, featured_id={featured_artist_id}")

    return track_entry

def build_ranking_entry(base, request, spotify_data, now):
    artist_name_clean = normalize_name(base["artistName"])
    track_name_clean = normalize_name(base["trackName"])

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

    logging.debug(f"📊 Ranking entry built: {ranking_entry}")
    return ranking_entry

def build_final_json(enriched_tracks, request, now):
    seen_artists = {}
    description_cache = {}
    artists = []
    tracks = []
    rankings = []

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
        featured_artist_id = spotify_data.get("featured_artist_id")
        featured_artist_name = base.get("featured_artist") or spotify_data.get("featured_artist_name")

        if featured_artist_id and featured_artist_name:
            featured_name_clean = normalize_name(featured_artist_name)
            if featured_name_clean not in seen_artists:
                logging.info(f"🎤 Adding featured artist: {featured_name_clean}")

                # 🔍 Try to fetch artwork for featured artist
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

        tracks.append(track_entry)
        rankings.append(ranking_entry)

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

    logging.info(f"📦 Final JSON built with {len(tracks)} tracks and {len(artists)} artists.")
    return final_json, tracks, artists

