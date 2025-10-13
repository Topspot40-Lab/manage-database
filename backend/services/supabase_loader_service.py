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
    return {"decade": decade, "genre": genre, "language": lang, "rankings": payload}

# ──────────────────────────────────────────────────────────────
# Collection Loader
# ──────────────────────────────────────────────────────────────

def load_collection(db, slug: str, tts_language: str):
    """Load ranked track data for a collection by slug or name."""
    lang = tts_language.lower().replace("-", "")
    slug_norm = slug.strip().lower()

    # ── 1️⃣ Find the collection by slug or name ─────────────────────
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
    # ---- 2) Fetch ranked tracks (joined with Track + Artist) ----
    stmt = (
        select(
            CollectionTrackRanking.ranking,
            Track.id,  # will be available as key "id"
            Track.track_name,  # "track_name"
            Artist.artist_name,  # "artist_name"
            Track.album_artwork,  # "album_artwork"
            Track.year_released,  # "year_released"
        )
        .join(Track, Track.id == CollectionTrackRanking.track_id)
        .join(Artist, Artist.id == Track.artist_id)
        .where(CollectionTrackRanking.collection_id == coll.id)
        .order_by(CollectionTrackRanking.ranking)
    )

    rows = db.exec(stmt).all()

    # ---- 3) Build structured result ----
    tracks = []
    for r in rows:
        row = getattr(r, "_mapping", r)  # Row or RowMapping
        tracks.append({
            "rank": row["ranking"],
            "trackId": row["id"],  # from Track.id
            "trackName": row["track_name"],
            "artistName": row["artist_name"],
            "yearReleased": row["year_released"],
            "albumArtwork": row["album_artwork"],
        })

    # ── 4️⃣ Return JSON payload ─────────────────────────────────────
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
