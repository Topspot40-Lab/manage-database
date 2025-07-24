# builders/json_builder.py
import json
import logging
from backend.services.spotify.track_search import get_spotify_artist_info
from backend.utils.json_helpers import normalize_name, clean_text_field
from backend.builders.track_builder import build_track_entry

logger = logging.getLogger(__name__)

from backend.utils.logger_factory import get_step_logger
logger_step4a = get_step_logger("STEP_4.A")
logger_step4b = get_step_logger("STEP_4.B")
logger_step4c = get_step_logger("STEP_4.C")
logger_step4d = get_step_logger("STEP_4.D")
logger_step4e = get_step_logger("STEP_4.E")


def build_final_json(enriched_tracks, request, now, is_test_mode=False):
    seen_artists = set()
    artists = []
    tracks = []
    rankings = []

    valid_tracks = [
        t for t in enriched_tracks
        if t.get("spotify_data") and t["spotify_data"].get("spotify_track_id")
    ]

    for vt in valid_tracks:
        tn = vt.get("track_name", "")
        an = vt.get("artist_name", "")
        if ".." in tn or ".." in an:
            logger_step4a.warning(f"⚠️ Suspicious field: track_name='{tn}', artist_name='{an}'")

    dropped = [t for t in enriched_tracks if t not in valid_tracks]
    for d in dropped:
        logger_step4a.warning(
            f"🗑️ Dropped from final: '{d.get('track_name')}' by '{d.get('artist_name')}' — missing Spotify ID"
        )

    for i, t in enumerate(valid_tracks, start=1):
        t["rank"] = i

    for base in valid_tracks:
        spotify_data = base.get("spotify_data", {})

        if is_test_mode:
            logger_step4a.debug(f"[TEST MODE] Using Spotify metadata for: {base.get('track_name')} by {base.get('artist_name')}")
        elif spotify_data:
            logger_step4a.debug(f"🎷 Enrich OK: '{base.get('track_name')}' by '{base.get('artist_name')}'")
        else:
            logger_step4a.warning(f"⚠️ Missing spotify_data for '{base.get('track_name')}'")

        base.pop("intro", None)
        track_entry = build_track_entry(base, request, spotify_data, now, is_test_mode)
        logger_step4c.debug(f"[🧪 TRACK ENTRY KEYS] {track_entry.keys()}")
        logger_step4c.debug(f"[🧪 TRACK ENTRY FIELDS] {json.dumps(track_entry, indent=2)}")

        track_entry.pop("intro", None)
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
            "intro": clean_text_field(base.get("intro")),
            "ranking_date": now.split("T")[0],
        })

        # Add main artist
        artist_name = normalize_name(track_entry.get("artist_name"))
        artist_id = track_entry.get("spotify_artist_id")
        artist_key = (artist_name, artist_id or "unknown")

        if artist_key not in seen_artists:
            artist_info = get_spotify_artist_info(artist_name)

            artists.append({
                "artist_name": artist_name,
                "spotify_artist_id": artist_id,
                "artist_artwork": artist_info.get("artist_artwork") if artist_info else None,
                "artist_description": artist_info.get("artist_description") if artist_info else None,
                "not_on_spotify": not bool(artist_info)
            })
            seen_artists.add(artist_key)

        # Add featured artist
        feat_name = normalize_name(track_entry.get("featured_artist") or "")
        feat_id = track_entry.get("featured_artist_id")
        feat_key = (feat_name, feat_id or "unknown")

        if feat_name and feat_id and feat_key not in seen_artists:
            artist_info = get_spotify_artist_info(feat_name)

            artists.append({
                "artist_name": feat_name,
                "spotify_artist_id": feat_id,
                "artist_artwork": artist_info.get("artist_artwork") if artist_info else None,
                "artist_description": artist_info.get("artist_description") if artist_info else None,
                "not_on_spotify": not bool(artist_info)
            })
            seen_artists.add(feat_key)

    logger_step4e.debug("🧱 [STEP_4.E] Assembling final JSON...")
    final_json = {
        "language": request.language,
        "category": request.decade,
        "genre": request.genre,
        "generated_at": now,
        "core_tables": {
            "genre": [{"genre_name": request.genre}],
            "decade": [{"decade_name": request.decade}],
            "artist": artists,
        },
        "track_tables": {
            "track": tracks,
            "tracklist": [{
                "name": "TopSpot Autogen",
                "curator": "Mr. Ed",
                "is_official": True,
                "language": request.language[:2],
                "notes": f"Generated for {request.genre} - {request.decade}",
                "created_at": now,
            }],
        },
        "ranking_tables": {
            "track_ranking": rankings
        }
    }

    logger_step4e.debug(
        f"🌟 [STEP_4.E] JSON build complete: {len(tracks)} tracks, "
        f"{len(artists)} unique artists, {len(rankings)} rankings."
    )

    return final_json, tracks, artists
