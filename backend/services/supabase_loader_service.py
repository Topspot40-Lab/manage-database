# backend/services/supabase_loader_service.py
from __future__ import annotations
import logging
from sqlmodel import Session, select

from backend.services.db_queries import get_decade_genre, get_rankings_for_combo
from backend.utils.naming import normalize_language_code_canon
from backend.services.localization import get_localized_texts
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename
)

from sqlalchemy import select, func
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
# 1️⃣ DECADE + GENRE LOADER
# ──────────────────────────────────────────────────────────────
def load_decade_genre(db: Session, decade: str, genre: str, tts_language: str):
    lang = normalize_language_code_canon(tts_language)

    dg = get_decade_genre(db, decade, genre)
    if not dg:
        raise HTTPException(
            status_code=404,
            detail=f"No DecadeGenre found for {decade}/{genre}"
        )

    rankings = get_rankings_for_combo(db, dg.id)

    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail")
    artist_bucket = bucket_for(lang, "artist")

    payload = []

    for r in rankings:
        track: Track = db.get(Track, r.track_id)
        if not track:
            continue

        artist: Artist | None = None
        if getattr(track, "artist_id", None):
            artist = db.get(Artist, track.artist_id)

        # narration text
        intro_text, detail_text = get_localized_texts(db, lang, r, track)

        # audio filenames
        intro_filename  = build_intro_filename(decade, genre, r.ranking)
        detail_filename = build_detail_filename(track.spotify_track_id)
        artist_filename = build_artist_filename(artist.spotify_artist_id) if artist else None

        payload.append({
            # ranking + identity
            "rank": r.ranking,
            "trackName": track.track_name,
            "artistName": _artist_display_name(track, artist),

            # narration
            "intro": intro_text,
            "detail": detail_text,
            "artistDescription": getattr(artist, "artist_description", None) if artist else None,

            # NEW ⭐ artist artwork (from Artist table)
            "artistArtwork": getattr(artist, "artist_artwork", None) if artist else None,

            # TTS audio keys
            "introKey":  {"bucket": intro_bucket,  "key": key_for("intro", intro_filename)},
            "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)} if detail_filename else None,
            "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,

            # playback
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
def load_collection(db, slug: str, tts_language: str):
    lang = tts_language.lower().replace("-", "")
    slug_norm = slug.strip().lower()

    # Resolve collection
    coll = db.exec(select(Collection).where(func.lower(Collection.slug) == slug_norm)).first()
    if not coll:
        coll = db.exec(select(Collection).where(func.lower(Collection.name) == slug_norm)).first()
    if coll is not None and not isinstance(coll, Collection):
        coll = coll[0]
    if not coll:
        raise HTTPException(status_code=404, detail=f"Collection not found for '{slug}'")

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
            Artist.artist_artwork,           # ⭐ NEW — include artist_artwork
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

        # Fetch full track + ranking
        track = db.get(Track, row["id"])
        ranking = db.exec(
            select(CollectionTrackRanking)
            .where(CollectionTrackRanking.collection_id == coll.id)
            .where(CollectionTrackRanking.track_id == track.id)
        ).first()

        artist = db.get(Artist, track.artist_id)

        # narration
        intro_text, detail_text = get_localized_texts(db, lang, ranking, track)

        intro_filename  = build_intro_filename(coll.slug, "collection", row["ranking"])
        detail_filename = build_detail_filename(track.spotify_track_id)
        artist_filename = build_artist_filename(artist.spotify_artist_id) if artist else None

        tracks.append({
            "rank": row["ranking"],
            "trackId": track.id,
            "trackName": track.track_name,
            "artistName": artist.artist_name,
            "artistDescription": artist.artist_description,

            # NEW ⭐ artist artwork from Artist table
            "artistArtwork": artist.artist_artwork,

            # narration
            "intro": intro_text,
            "detail": detail_text,

            # audio keys
            "introKey":  {"bucket": intro_bucket,  "key": key_for("intro", intro_filename)},
            "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)},
            "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,

            # playback + metadata
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
