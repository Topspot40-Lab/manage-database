# backend/services/supabase_loader_service.py
from __future__ import annotations
import logging
from sqlmodel import Session, select


from backend.utils.naming import normalize_language_code_canon
from backend.services.localization import get_localized_texts
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename
)

from sqlalchemy import func
from fastapi import HTTPException
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track, Artist

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Global in-memory cache
# ──────────────────────────────────────────────────────────────
current_decade_genre_tracks: list[dict] = []


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _artist_display_name(track: Track, artist: Artist | None) -> str:
    return (
        getattr(artist, "artist_name", None)
        or getattr(track, "artist_display_name", None)
        or getattr(track, "artist_name", None)
        or "Unknown Artist"
    )

# ──────────────────────────────────────────────────────────────
# 1️⃣ FIXED — DECADE + GENRE LOADER (correct schema)
# ──────────────────────────────────────────────────────────────
from backend.models.dbmodels import Decade, Genre, DecadeGenre, TrackRanking

def load_decade_genre(db: Session, decade: str, genre: str, tts_language: str):
    lang = normalize_language_code_canon(tts_language)

    # 1. Resolve decade
    dec = db.exec(select(Decade).where(Decade.slug == decade)).first()
    if not dec:
        raise HTTPException(404, f"Decade not found: {decade}")

    # 2. Resolve genre
    gen = db.exec(select(Genre).where(Genre.slug == genre)).first()
    if not gen:
        raise HTTPException(404, f"Genre not found: {genre}")

    # 3. Resolve decade_genre row
    dg = db.exec(
        select(DecadeGenre)
        .where(DecadeGenre.decade_id == dec.id)
        .where(DecadeGenre.genre_id == gen.id)
    ).first()

    if not dg:
        raise HTTPException(
            404,
            f"No decade_genre entry exists for decade={decade}, genre={genre}"
        )

    # 4. Load all rankings for this combo
    rankings = db.exec(
        select(TrackRanking)
        .where(TrackRanking.decade_genre_id == dg.id)
        .order_by(TrackRanking.ranking)
    ).all()

    # 5. TTS buckets
    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail")
    artist_bucket = bucket_for(lang, "artist")

    payload = []

    # 6. Build payload (keep your existing logic unchanged)
    for r in rankings:
        track: Track = db.get(Track, r.track_id)
        if not track:
            continue

        artist: Artist | None = None
        if getattr(track, "artist_id", None):
            artist = db.get(Artist, track.artist_id)

        # narration (your existing localization)
        intro_text, detail_text = get_localized_texts(db, lang, r, track)

        intro_filename  = build_intro_filename(decade, genre, r.ranking)
        detail_filename = build_detail_filename(track.spotify_track_id)
        artist_filename = (
            build_artist_filename(artist.spotify_artist_id)
            if artist else None
        )

        payload.append({
            "rank": r.ranking,
            "trackName": track.track_name,
            "artistName": _artist_display_name(track, artist),

            "intro": intro_text,
            "detail": detail_text,
            "artistDescription": getattr(artist, "artist_description", None) if artist else None,

            "artistArtwork": getattr(artist, "artist_artwork", None) if artist else None,

            "introKey": {
                "bucket": intro_bucket,
                "key": key_for("intro", intro_filename)
            },
            "detailKey": {
                "bucket": detail_bucket,
                "key": key_for("detail", detail_filename)
            } if detail_filename else None,
            "artistKey": {
                "bucket": artist_bucket,
                "key": key_for("artist", artist_filename)
            } if artist_filename else None,

            "spotifyTrackId": track.spotify_track_id,
            "durationMs": track.duration_ms,
            "yearReleased": track.year_released,
            "albumArtwork": track.album_artwork,
        })

    logger.info(
        "✅ Loaded %d tracks for %s / %s (%s)",
        len(payload), decade, genre, lang
    )

    global current_decade_genre_tracks
    current_decade_genre_tracks = payload

    return {
        "decade": decade,
        "genre": genre,
        "language": lang,
        "rankings": payload,
    }

# ──────────────────────────────────────────────────────────────
# 2️⃣ COLLECTION LOADER
# ──────────────────────────────────────────────────────────────
def load_collection(db: Session, slug: str, tts_language: str):
    """
    Resolve a collection strictly by slug.
    Names are NOT used for lookups.
    """
    lang = normalize_language_code_canon(tts_language)
    slug_norm = slug.strip().lower()

    # Slug-only lookup
    coll = db.exec(
        select(Collection).where(func.lower(Collection.slug) == slug_norm)
    ).first()

    if not coll:
        raise HTTPException(404, f"Collection not found for slug '{slug}'")

    # Full ranking + track + artist
    stmt = (
        select(
            CollectionTrackRanking.ranking,
            Track.id,
            Track.track_name,
            Track.album_artwork,
            Track.year_released,
            Track.spotify_track_id,
            Track.duration_ms,
            Artist.artist_name,
            Artist.artist_description,
            Artist.artist_artwork,
        )
        .join(Track, Track.id == CollectionTrackRanking.track_id)
        .join(Artist, Artist.id == Track.artist_id)
        .where(CollectionTrackRanking.collection_id == coll.id)
        .order_by(CollectionTrackRanking.ranking)
    )

    rows = db.exec(stmt).all()

    # TTS buckets
    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail")
    artist_bucket = bucket_for(lang, "artist")

    tracks = []

    for r in rows:
        row = getattr(r, "_mapping", r)

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
        artist_filename = (
            build_artist_filename(artist.spotify_artist_id) if artist else None
        )

        tracks.append({
            "rank": row["ranking"],
            "trackId": track.id,
            "trackName": track.track_name,
            "artistName": artist.artist_name,
            "artistDescription": artist.artist_description,
            "artistArtwork": artist.artist_artwork,
            "intro": intro_text,
            "detail": detail_text,
            "introKey":  {"bucket": intro_bucket, "key": key_for("intro", intro_filename)},
            "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)},
            "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,
            "yearReleased": track.year_released,
            "albumArtwork": track.album_artwork,
            "spotifyTrackId": track.spotify_track_id,
            "durationMs": track.duration_ms,
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
