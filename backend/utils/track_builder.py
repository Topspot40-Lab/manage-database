from backend.utils.mode_utils import determine_mode_flag_basic, ModeFlag
from backend.services.track_generator import format_track_display_name
from backend.utils.json_helpers import parse_featured_artists, normalize_name


def build_track_entry(base, request, spotify_data, now):
    artist_name_raw = base["artistName"]
    track_name_raw = base["trackName"]

    # Parse and normalize names
    artist_name_clean, featured_artist_name = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    featured_artist = normalize_name(featured_artist_name) if featured_artist_name else None
    track_name_clean = normalize_name(track_name_raw)

    # Mode flag
    mode_flag: ModeFlag = determine_mode_flag_basic(artist_name_raw)

    track_display_name = format_track_display_name(
        track_name_clean,
        featured_artist_name,
        mode_flag.value,
    )

    return {
        "trackName": track_name_clean,
        "artistName": artist_name_clean,
        "featuredArtist": featured_artist,
        "featuredArtistId": spotify_data.get("featured_artist_id"),
        "trackDisplayName": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotifyTrackId": spotify_data.get("spotify_track_id"),
        "spotifyArtistId": spotify_data.get("artist_id"),
        "modeFlag": mode_flag.value,
        "durationMs": spotify_data.get("duration_ms"),
        "popularity": spotify_data.get("popularity"),
        "albumArtwork": spotify_data.get("album_artwork"),
        "yearReleased": int(base["yearReleased"]),
        "isExplicit": False,
        "createdAt": now,
        "intro": base.get("intro"),
        "detail": base.get("detail"),
        "detailMp3Url": base.get("detail_mp3_url"),
        "notOnSpotify": spotify_data.get("not_on_spotify", False),
    }


def build_final_json(enriched_tracks, request, now):
    """Return (final_json, track_entries, artist_entries) tuple.

    The JSON structure mirrors the legacy format expected by the
    generate_json router, grouping arrays under the ``track_tables`` key.
    """

    seen_artists = {}
    artists = []
    tracks = []
    rankings = []

    for base in enriched_tracks:
        spotify_data = base["spotifyData"]
        track_entry = build_track_entry(base, request, spotify_data, now)
        tracks.append(track_entry)

        rankings.append(
            {
                "trackId": track_entry["spotifyTrackId"],
                "rank": base["rank"],
                "genre": request.genre,
                "decade": request.decade,
                "createdAt": now,
            }
        )

        artist_id = track_entry["spotifyArtistId"]
        if artist_id and artist_id not in seen_artists:
            seen_artists[artist_id] = track_entry["artistName"]
            artists.append(
                {
                    "artistName": track_entry["artistName"],
                    "spotifyArtistId": artist_id,
                    "artistArtwork": spotify_data.get("artist_artwork"),
                    "artistDescription": spotify_data.get("artist_description"),
                }
            )

    final_json = {
        "language": request.language,
        "category": request.decade,
        "genre": request.genre,
        "generatedAt": now,
        "track_tables": {
            "track": tracks,
            "artist": artists,
            "ranking": rankings,
        },
    }

    return final_json, tracks, artists
