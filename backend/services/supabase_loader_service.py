# backend/services/supabase_loader_service.py
from __future__ import annotations
import logging
from sqlmodel import Session, select

from backend.services.db_queries import get_decade_genre, get_rankings_for_combo
from backend.utils.naming import normalize_language_code_canon
from backend.services.localization import get_localized_texts
from backend.services.playback_helpers import bucket_for, key_for, build_intro_filename, build_detail_filename, build_artist_filename

from sqlalchemy import select, func
from fastapi import HTTPException
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track, Artist

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Global in-memory cache for currently loaded tracks
# ──────────────────────────────────────────────────────────────
current_decade_genre_tracks: list[dict] = []


# ──────────────────────────────────────────────────────────────
# Generic helpers
# ──────────────────────────────────────────────────────────────
def _artist_display_name(track: Track, artist: Artist | None) -> str:
    """Consistent display-name fallback chain."""
    return (
        getattr(artist, "artist_name", None)
        or getattr(track, "artist_display_name", None)
        or getattr(track, "artist_name", None)
        or "Unknown Artist"
    )

# ──────────────────────────────────────────────────────────────
# Decade/Genre Loader
# ──────────────────────────────────────────────────────────────
def load_decade_genre(db: Session, decade: str, genre: str, tts_language: str):
    lang = normalize_language_code_canon(tts_language)
    dg = get_decade_genre(db, decade, genre)
    if not dg:
        raise HTTPException(status_code=404, detail=f"No DecadeGenre found for {decade}/{genre}")

    rankings = get_rankings_for_combo(db, dg.id)
    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail")
    artist_bucket = bucket_for(lang, "artist")

    payload = []
    for r in rankings:
        track = db.get(Track, r.track_id)
        if not track:
            continue
        artist = db.get(Artist, track.artist_id) if getattr(track, "artist_id", None) else None

        intro_text, detail_text = get_localized_texts(db, lang, r, track)
        intro_filename  = build_intro_filename(decade, genre, r.ranking)
        detail_filename = build_detail_filename(track.spotify_track_id)
        artist_filename = build_artist_filename(artist.spotify_artist_id) if artist else None

        payload.append({
            "rank": r.ranking,
            "trackName": track.track_name,
            "artistName": _artist_display_name(track, artist),
            "intro": intro_text,
            "detail": detail_text,
            "artistDescription": getattr(artist, "artist_description", None) if artist else None,
            "introKey":  {"bucket": intro_bucket,  "key": key_for("intro", intro_filename)},
            "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)} if detail_filename else None,
            "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,
            "albumArtwork": track.album_artwork,
        })
    logger.info("✅ Loaded %d tracks for %s / %s (%s)", len(payload), decade, genre, lang)

    global current_decade_genre_tracks
    current_decade_genre_tracks = payload

    return {"decade": decade, "genre": genre, "language": lang, "rankings": payload}

# ──────────────────────────────────────────────────────────────
# Collection Loader
# ──────────────────────────────────────────────────────────────

def load_collection(db, slug: str, tts_language: str):
    lang = tts_language.lower().replace("-", "")
    slug_norm = slug.strip().lower()

    # ── 1️⃣ Resolve the collection record ─────────────────────
    coll = db.exec(
        select(Collection).where(func.lower(Collection.slug) == slug_norm)
    ).first()
    if not coll:
        coll = db.exec(
            select(Collection).where(func.lower(Collection.name) == slug_norm)
        ).first()
    if coll is not None and not isinstance(coll, Collection):
        coll = coll[0]
    if not coll:
        raise HTTPException(status_code=404, detail=f"Collection not found for '{slug}'")

    # ── 2️⃣ Query: Track + Artist + FULL RANKING + NARRATION ─────────────────────
    stmt = (
        select(
            CollectionTrackRanking.ranking,
            Track.id,
            Track.track_name,
            Track.album_artwork,
            Track.year_released,
            Track.spotify_track_id,

            Artist.artist_name,
            Artist.artist_description,     # ⭐ ADD THIS
        )
        .join(Track, Track.id == CollectionTrackRanking.track_id)
        .join(Artist, Artist.id == Track.artist_id)
        .where(CollectionTrackRanking.collection_id == coll.id)
        .order_by(CollectionTrackRanking.ranking)
    )

    rows = db.exec(stmt).all()

    # ── 3️⃣ Build payload with narration ─────────────────────
    from backend.services.localization import get_localized_texts
    from backend.services.playback_helpers import (
        bucket_for, key_for, build_intro_filename,
        build_detail_filename, build_artist_filename
    )

    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail")
    artist_bucket = bucket_for(lang, "artist")

    tracks = []
    for r in rows:
        row = getattr(r, "_mapping", r)

        # Fetch full Track + Ranking record for narration
        track = db.get(Track, row["id"])
        ranking = db.exec(
            select(CollectionTrackRanking)
            .where(CollectionTrackRanking.collection_id == coll.id)
            .where(CollectionTrackRanking.track_id == track.id)
        ).first()

        artist = db.get(Artist, track.artist_id)

        intro_text, detail_text = get_localized_texts(db, lang, ranking, track)

        intro_filename  = build_intro_filename(coll.slug, "collection", row["ranking"])
        detail_filename = build_detail_filename(track.spotify_track_id)
        artist_filename = build_artist_filename(artist.spotify_artist_id) if artist else None

        tracks.append({
            "rank": row["ranking"],
            "trackId": track.id,
            "trackName": track.track_name,
            "artistName": artist.artist_name,
            "artistDescription": artist.artist_description,  # ⭐ NOW INCLUDED

            "intro": intro_text,
            "detail": detail_text,

            "introKey":  {"bucket": intro_bucket,  "key": key_for("intro", intro_filename)},
            "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)},
            "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,

            "yearReleased": track.year_released,
            "albumArtwork": track.album_artwork,
            "spotifyTrackId": track.spotify_track_id,
        })

    return {
        "collection": {
            "id": coll.id,
            "name": coll.name,
            "slug": coll.slug,
        },
        "language": lang,
        "totalTracks": len(tracks),
        "tracks": tracks,
    }
