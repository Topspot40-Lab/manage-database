# backend/services/collections_serialize.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

def _to_int_or_none(v: Any) -> Optional[int]:
    try: return int(v)
    except Exception: return None

def _to_bool(v: Any) -> bool:
    if isinstance(v, bool): return v
    s = str(v).strip().lower()
    if s in {"true","1","yes"}: return True
    if s in {"false","0","no"}: return False
    return False

def _resolve_album_art(t: dict) -> Optional[str]:
    return (
        t.get("album_art_url") or
        t.get("album_artwork") or
        t.get("albumImageUrl") or
        t.get("album_image_url") or
        t.get("albumArtUrl") or
        None
    )

def serialize_collection_output(
    *,
    slug: str,
    display_name: str,
    language_code: str,
    tracks: List[Dict[str, Any]],
    ranking: List[Dict[str, Any]],
    artist_tbl: List[Dict[str, Any]],
) -> Dict[str, Any]:
    created_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    artists_legacy = [
        {
            "artist_name": a.get("artist_name"),
            "spotify_artist_id": a.get("spotify_artist_id"),
            "artist_artwork": a.get("artist_artwork"),
            "artist_description": a.get("artist_description"),
        }
        for a in artist_tbl
    ]

    tracks_legacy = []
    for t in tracks:
        mf = (t.get("mode_flag") or "SOLO").upper()
        tracks_legacy.append({
            "track_name": t.get("track_name"),
            "artist_name": t.get("artist_name"),
            "artist_display_name": t.get("artist_display_name"),
            "featured_artist": t.get("featured_artist") or None,
            "featured_artist_id": t.get("featured_artist_id") or None,
            "track_display_name": t.get("track_display_name"),
            "genre": t.get("genre"),
            "decade": t.get("decade"),
            "spotify_track_id": t.get("spotify_track_id"),
            "spotify_artist_id": t.get("spotify_artist_id") or t.get("artist_id"),
            "mode_flag": mf,
            "duration_ms": _to_int_or_none(t.get("duration_ms")),
            "popularity": _to_int_or_none(t.get("popularity")),
            "album_artwork": t.get("album_artwork") or _resolve_album_art(t),
            "album_name": t.get("album_name"),
            "year_released": _to_int_or_none(t.get("year_released")),
            "is_explicit": _to_bool(t.get("is_explicit", False)),
            "created_at": created_iso,
            "detail": t.get("detail") or None,
        })

    rankings_legacy = [
        {
            "rank": r.get("rank"),
            "spotify_track_id": r.get("spotify_track_id"),
            "track_id": r.get("track_id"),
            "intro": r.get("intro"),
            "created_at": created_iso,
        }
        for r in ranking
    ]

    tracks_camel = [
        {
            "rank": int(t.get("rank") or 0),
            "trackName": t.get("track_name"),
            "artistName": t.get("artist_name"),
            "artistDisplayName": t.get("artist_display_name"),
            "featuredArtist": t.get("featured_artist") or None,
            "featuredArtistId": t.get("featured_artist_id") or None,
            "trackDisplayName": t.get("track_display_name"),
            "genre": t.get("genre"),
            "decade": t.get("decade"),
            "spotifyTrackId": t.get("spotify_track_id"),
            "spotifyArtistId": t.get("spotify_artist_id") or t.get("artist_id"),
            "modeFlag": (t.get("mode_flag") or "SOLO").upper(),
            "durationMs": _to_int_or_none(t.get("duration_ms")),
            "popularity": _to_int_or_none(t.get("popularity")),
            "albumArtwork": t.get("album_artwork") or _resolve_album_art(t),
            "albumName": t.get("album_name"),
            "yearReleased": _to_int_or_none(t.get("year_released")),
            "isExplicit": _to_bool(t.get("is_explicit", False)),
            "createdAt": created_iso,
            "detail": t.get("detail") or None,
        }
        for t in tracks
    ]

    return {
        "collection": {
            "name": display_name,
            "slug": slug,
            "type": "COLLECTION",
            "language": language_code,
            "created_at": created_iso,
        },
        "artist": artists_legacy,
        "track": tracks_legacy,
        "track_ranking": rankings_legacy,
        "trackRanking": [
            {
                "rank": r.get("rank"),
                "spotifyTrackId": r.get("spotify_track_id"),
                "trackId": r.get("track_id"),
                "intro": r.get("intro"),
            }
            for r in ranking
        ],
        "tracks": tracks_camel,
    }
