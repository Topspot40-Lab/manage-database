from backend.utils.mode_utils import ModeFlag
from backend.utils.json_helpers import parse_featured_artists, normalize_name
import json
import logging
import re  # make sure it's imported at top if not already
from backend.services.spotify.track_search import get_spotify_artist_info
from backend.utils.json_helpers import clean_text_field
logger = logging.getLogger(__name__)

from backend.utils.logger_factory import get_step_logger

logger_step4a = get_step_logger("STEP_4.A")
logger_step4b = get_step_logger("STEP_4.B")
logger_step4c = get_step_logger("STEP_4.C")
logger_step4d = get_step_logger("STEP_4.D")
logger_step4e = get_step_logger("STEP_4.E")
#
# def normalize_keys(base: dict) -> dict:
#     """Ensure consistent snake_case keys for downstream processing."""
#     return {
#         "track_name": base.get("track_name") or base.get("trackName"),
#         "artist_name": base.get("artist_name") or base.get("artistName"),
#         "year_released": base.get("year_released") or base.get("yearReleased"),
#         "rank": base.get("rank"),
#         "intro": base.get("intro"),
#         "detail": base.get("detail"),
#         **base  # Preserve any other existing fields
#     }

def clean_fallback_id(name: str) -> str:
    base = normalize_name(name)
    base = re.sub(r"\W+", "_", base)        # Replace non-word chars with _
    base = re.sub(r"_+", "_", base)         # Collapse multiple underscores
    base = base.strip("_")                  # Trim leading/trailing _
    return f"test_{base}"



def build_track_entry(base, request, spotify_data, now, is_test_mode=False):

    logger_step4b.debug(f"[build_track_entry] incoming base keys: {list(base.keys())}")

    if is_test_mode:
        logger_step4b.debug(
            "\n🧪 [STEP_4.B] TEST MODE — build_track_entry\n"
            f"   🏅 Rank: {base.get('rank')}\n"
            f"   🎼 Track: '{base.get('track_name')}', Artist: '{base.get('artist_name')}'\n"
            f"   🐛 Logger: {logger_step4b.name}, Level: {logger_step4b.getEffectiveLevel()}\n"
        )
    else:
        logger_step4b.debug(
            "\n🔧 [STEP_4.B] Starting build_track_entry\n"
            f"   🏅 Rank: {base.get('rank')}\n"
            f"   🎼 Track: '{base.get('track_name')}', Artist: '{base.get('artist_name')}'\n"
            f"   🐛 Logger: {logger_step4b.name}, Level: {logger_step4b.getEffectiveLevel()}\n"
            f"   📆 Spotify data:\n{json.dumps(spotify_data, indent=4)}"
        )

    if not base.get("artist_name"):
        raise ValueError(f"❌ Missing 'artist_name' in base: {base}")
    if not base.get("track_name"):
        raise ValueError(f"❌ Missing 'track_name' in base: {base}")
    if not base.get("year_released"):
        raise ValueError(f"❌ Missing 'year_released' in base: {base}")

    artist_name_raw = base["artist_name"]
    track_name_raw = base["track_name"]
    year_released = base["year_released"]

    # Parse artist names
    artist_name_clean, featured_artist_name_raw, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)

    logger_step4b.debug(f"🔍 base['featured_artist_name'] = {base.get('featured_artist_name')}")

    if not featured_artist_name_raw:
        featured_artist_name_raw = base.get("featured_artist_name")

    logger_step4b.debug(f"🎯 Final featured_artist_name_raw = {featured_artist_name_raw}")

    track_name_clean = normalize_name(track_name_raw)
    track_display_name = track_name_clean
    if featured_artist_name_raw:
        track_display_name += f" (feat. {featured_artist_name_raw})"

    logger_step4b.debug(f"🎵 track_display_name = '{track_display_name}'")

    track_name_clean = normalize_name(track_name_raw)
    track_display_name = track_name_clean
    if featured_artist_name_raw:
        track_display_name += f" (feat. {featured_artist_name_raw})"

    track_display_name = track_name_clean

    mode_flag_str = base.get("mode_flag", "unknown")
    try:
        mode_flag = ModeFlag(mode_flag_str)
    except ValueError:
        logger_step4b.warning(f"⚠️ Invalid mode_flag '{mode_flag_str}' — defaulting to 'unknown'")
        mode_flag = ModeFlag.UNKNOWN

    logger_step4b.debug(f"🧽 Normalized: '{track_name_clean}' by '{artist_name_clean}', Mode: {mode_flag.value}")
    logger_step4b.debug(f"🎨 Display Name: {track_display_name}, Featured: {featured_artist_name_raw}")
    logger_step4b.debug(f"🖼️ Artist Display Name: {base.get('artist_display_name')}")

    # Clean detail field
    detail_cleaned = clean_text_field(base.get("detail"))

    result = {
        "rank": base.get("rank"),
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "artist_display_name": base.get("artist_display_name", artist_name_raw),
        "featured_artist": base.get("featured_artist_name", featured_artist_name_raw),
        "featured_artist_id": spotify_data.get("featured_artist_id"),
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotify_track_id": spotify_data.get("spotify_track_id"),
        "spotify_artist_id": (
                spotify_data.get("artist_id")
                or base.get("artist_id")
                or clean_fallback_id(artist_name_raw)
        ),
        "mode_flag": mode_flag.value,
        "duration_ms": spotify_data.get("duration_ms"),
        "popularity": spotify_data.get("popularity"),
        "album_artwork": spotify_data.get("album_artwork"),
        "album_name": spotify_data.get("album_name"),  # ✅ added here
        "year_released": year_released,
        "is_explicit": False,
        "created_at": now,
        "detail": detail_cleaned
    }

    logger_step4b.debug(
        f"✅ [STEP_4.B] Track entry complete for Rank {base.get('rank')}: {result['track_name']} by {result['artist_name']}"
    )

    return result

def build_final_json(enriched_tracks, request, now, is_test_mode=False):
    seen_artists = set()
    artists = []
    tracks = []
    rankings = []

    # ─────────────────────────────────────────────────────────────────────────────
    # 🧼 STEP 4 PREP — Filter tracks with missing Spotify ID & reassign rank
    # ─────────────────────────────────────────────────────────────────────────────
    valid_tracks = [
        t for t in enriched_tracks
        if t.get("spotify_data") and t["spotify_data"].get("spotify_track_id")
    ]

    # 🔍 Check for suspicious fields
    for vt in valid_tracks:
        tn = vt.get("track_name", "")
        an = vt.get("artist_name", "")
        if ".." in tn or ".." in an:
            logger_step4a.warning(f"⚠️ Suspicious field: track_name='{tn}', artist_name='{an}'")

    # Optional: log dropped ones
    dropped = [t for t in enriched_tracks if t not in valid_tracks]
    for d in dropped:
        logger_step4a.warning(
            f"🗑️ Dropped from final: '{d.get('track_name')}' by '{d.get('artist_name')}' — missing Spotify ID"
        )

    # 🔢 Reassign rank 1..N
    for i, t in enumerate(valid_tracks, start=1):
        t["rank"] = i

    for base in valid_tracks:

        spotify_data = base.get("spotify_data", {})

        # ─────────────────────────────────────────────────────────────────────────────
        # 🎧 STEP 4.A — Logging Spotify metadata usage
        # ─────────────────────────────────────────────────────────────────────────────
        if is_test_mode:
            logger_step4a.debug(
                f"[TEST MODE] Using Spotify metadata for: "
                f"{base.get('track_name')} by {base.get('artist_name')}"
            )
        else:
            if spotify_data:
                logger_step4a.debug(
                    f"🎷 Enrich OK: '{base.get('track_name')}' by '{base.get('artist_name')}'"
                )
            else:
                logger_step4a.warning(
                    f"⚠️ Missing spotify_data for '{base.get('track_name')}'"
                )

        # ─────────────────────────────────────────────────────────────────────────────
        # 🎵 STEP 4.B — Build individual track record
        # ─────────────────────────────────────────────────────────────────────────────
        logger_step4b.debug(
            f"🧪 base[{base.get('rank')}]: artist_name={base.get('artist_name')}, "
            f"display_name={base.get('artist_display_name')}, featured={base.get('featured_artist_name')}"
        )

        track_entry = build_track_entry(base, request, spotify_data, now, is_test_mode)
        tracks.append(track_entry)

        logger_step4b.debug(
            f"🎭 Mode flag: {track_entry.get('mode_flag')} for {track_entry.get('track_name')}"
        )

        # ─────────────────────────────────────────────────────────────────────────────
        # 🏆 STEP 4.C — Add ranking row
        # ─────────────────────────────────────────────────────────────────────────────
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

        # ─────────────────────────────────────────────────────────────────────────────
        # 🎤 STEP 4.D — Add MAIN artist
        # ─────────────────────────────────────────────────────────────────────────────
        raw_main_artist_name = track_entry.get("artist_name")
        norm_main_artist_name = normalize_name(raw_main_artist_name)
        main_artist_id = track_entry.get("spotify_artist_id")

        logger_step4d.debug(
            f"🎯 MAIN ARTIST check: raw={raw_main_artist_name}, normalized={norm_main_artist_name}, "
            f"id={main_artist_id}, seen={main_artist_id in seen_artists}"
        )

        artist_key = (norm_main_artist_name, main_artist_id or "unknown")

        if norm_main_artist_name and artist_key not in seen_artists:
            artist_info = get_spotify_artist_info(norm_main_artist_name)

            if not artist_info:
                logger_step4d.warning(f"❌ No Spotify info found for main artist: {norm_main_artist_name}")

            logger_step4d.debug(f"🎤 Adding main artist: {norm_main_artist_name} ({main_artist_id})")

            # Normalize name and build a deduplication key
            norm_main_artist_name = normalize_name(base.get("artist_name"))
            main_artist_id = spotify_data.get("spotify_artist_id")
            if norm_main_artist_name and main_artist_id:
                artist_key = f"{norm_main_artist_name.lower()}::{main_artist_id}"
            else:
                artist_key = norm_main_artist_name.lower()  # fallback if no Spotify ID

            if artist_key not in seen_artists:
                artists.append({
                    "artist_name": norm_main_artist_name,
                    "spotify_artist_id": main_artist_id,
                    "artist_artwork": artist_info.get("artist_artwork") if artist_info else None,
                    "artist_description": (
                        artist_info.get("artist_description")
                        if artist_info else base.get("artist_description") or spotify_data.get("artist_description")
                    ),
                    "not_on_spotify": not bool(artist_info),
                })
                seen_artists.add(artist_key)

        # ─────────────────────────────────────────────────────────────────────────────
        # 👤 STEP 4.D — Add FEATURED artist if present
        # ─────────────────────────────────────────────────────────────────────────────
        raw_feat_name = track_entry.get("featured_artist")
        norm_feat_name = normalize_name(raw_feat_name) if raw_feat_name else None
        feat_artist_id = track_entry.get("featured_artist_id")

        artist_key = (norm_feat_name, feat_artist_id or "unknown")

        logger_step4d.debug(
            f"👤 FEATURED ARTIST check: raw={raw_feat_name}, normalized={norm_feat_name}, "
            f"id={feat_artist_id}, seen={artist_key in seen_artists}"
        )

        if norm_feat_name and feat_artist_id and artist_key not in seen_artists:
            artist_info = get_spotify_artist_info(norm_feat_name)

            if not artist_info:
                logger_step4d.warning(f"❌ No Spotify info found for featured artist: {norm_feat_name}")

            logger_step4d.debug(f"👤 Adding featured artist: {norm_feat_name} ({feat_artist_id})")

            artists.append({
                "artist_name": norm_feat_name,
                "spotify_artist_id": feat_artist_id,
                "artist_artwork": artist_info.get("artist_artwork") if artist_info else None,
                "artist_description": artist_info.get("artist_description") if artist_info else None,
                "artist_mp3_url": None,
                "not_on_spotify": not bool(artist_info),
            })

            seen_artists.add(artist_key)

            logger_step4d.debug(
                f"🧾 Artist list so far (Rank {base.get('rank')}): {[a['artist_name'] for a in artists]}"
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # 🧱 STEP 4.E — Assemble the final JSON structure
    # ─────────────────────────────────────────────────────────────────────────────
    logger_step4e.debug("🧱 [STEP_4.E] Assembling final JSON...")
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

    logger_step4e.debug(
        f"🧾 Final JSON includes:\n"
        f"   🎵 Tracks: {len(tracks)}\n"
        f"   👨‍🎤 Main + Featured Artists: {len(artists)}\n"
        f"   🪪 Rankings: {len(rankings)}"
    )

    logger_step4e.debug(
        f"🌟 [STEP_4.E] JSON build complete: {len(tracks)} tracks, "
        f"{len(artists)} unique artists, {len(rankings)} rankings."
    )

    return final_json, tracks, artists
