import logging
from backend.services.spotify_service import get_spotify_data, determine_mode_flag, format_track_display_name
from utils.json_helpers import parse_featured_artists, normalize_name


def fetch_and_validate_tracks(base):
    artist_name_raw = base["artistName"]
    track_name_raw = base["trackName"]

    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    track_name_clean = normalize_name(track_name_raw)

    logging.info(f"🎯 Searching Spotify with: '{track_name_clean}' by '{artist_name_clean}'")

    return get_spotify_data(track_name_clean, artist_name_clean)


def process_artist(base, spotify_data, seen_artists, description_cache, language):
    from backend.services.xai_service import get_artist_description

    artist_name_raw = base["artistName"]
    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)

    if artist_name_clean in seen_artists:
        return None

    if artist_name_clean not in description_cache:
        logging.info(f"🔍 Fetching description for: {artist_name_clean}")
        desc = get_artist_description(artist_name_clean, language=language)
        if not desc:
            desc = "No biography available at this time."
        description_cache[artist_name_clean] = desc

    detail_mp3_url = (
        base.get("detail_mp3_url")
        if spotify_data and spotify_data.get("id")
        else "tts/detail_unavailable.mp3"
    )

    artist_entry = {
        "artist_name": artist_name_clean,
        "spotify_artist_id": spotify_data.get("artistId") if spotify_data else None,
        "artist_artwork": spotify_data.get("artistImage") if spotify_data else None,
        "artist_description": description_cache[artist_name_clean],
        "artist_mp3_url": detail_mp3_url,
        "not_on_spotify": not spotify_data or not spotify_data.get("id")
    }

    seen_artists[artist_name_clean] = True
    return artist_entry


def build_track_entry(base, request, spotify_data, now):
    artist_name_raw = base["artistName"]
    track_name_raw = base["trackName"]

    artist_name_clean, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    track_name_clean = normalize_name(track_name_raw)

    mode_flag, featured_artist_id = determine_mode_flag(artist_name_raw, spotify_data.get("artistNameCandidates", []))
    track_display_name = format_track_display_name(
        artist_name_clean, featured_artist_id, mode_flag.name
    )

    return {
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.category,
        "spotify_track_id": spotify_data.get("id") if spotify_data else None,
        "spotify_artist_id": spotify_data.get("artistId") if spotify_data else None,
        "mode_flag": mode_flag.value,
        "duration_ms": spotify_data.get("durationMs") if spotify_data else None,
        "popularity": spotify_data.get("popularity") if spotify_data else None,
        "album_artwork": spotify_data.get("trackImage") if spotify_data else None,
        "year_released": int(base["yearReleased"]),
        "is_explicit": False,
        "created_at": now,
        "detail": base.get("detail"),
        "detail_mp3_url": base.get("detail_mp3_url"),
        "not_on_spotify": not spotify_data or not spotify_data.get("id")
    }


def build_ranking_entry(base, request, spotify_data, now):
    artist_name_clean = normalize_name(base["artistName"])
    track_name_clean = normalize_name(base["trackName"])

    return {
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "spotify_track_id": spotify_data.get("id") if spotify_data else None,
        "genre": request.genre,
        "decade": request.category,
        "tracklist": "TopSpot Autogen",
        "rank": base["rank"],
        "intro": base.get("intro"),
        "intro_mp3_url": base.get("intro_mp3_url"),
        "ranking_date": now[:10]
    }

def build_final_json(enriched_tracks, request, now):
    seen_artists = {}
    description_cache = {}
    artists = []
    tracks = []
    rankings = []

    for base in enriched_tracks:
        spotify_data = fetch_and_validate_tracks(base)

        artist_entry = process_artist(
            base=base,
            spotify_data=spotify_data,
            seen_artists=seen_artists,
            description_cache=description_cache,
            language=request.language
        )

        if artist_entry:
            artists.append(artist_entry)

        track_entry = build_track_entry(base, request, spotify_data, now)
        ranking_entry = build_ranking_entry(base, request, spotify_data, now)

        tracks.append(track_entry)
        rankings.append(ranking_entry)

    return {
        "core_tables": {
            "genre": [{"genre_name": request.genre}],
            "decade": [{"decade_name": request.category}],
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
                    "notes": f"Generated for {request.category} - {request.genre}",
                    "created_at": now
                }
            ]
        },
        "ranking_tables": {
            "track_ranking": rankings
        }
    }
