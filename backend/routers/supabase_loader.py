# backend/routers/supabase_loader.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from backend.database import get_db
from backend.models.dbmodels import (
    Track,
    Artist,
    TrackRanking,
    Collection,
    CollectionTrackRanking,
)

logger = logging.getLogger("backend.supabase_loader")

router = APIRouter(
    prefix="/supabase",
    tags=["Supabase Loader"],
)

# -------------------------------------------------------------------
# Small helpers so we don't blow up if a column is named slightly
# differently in your models (spotify_id vs spotify_track_id, etc.)
# -------------------------------------------------------------------
def _safe_track_payload(rank: int, track: Track, artist: Artist) -> Dict[str, Any]:
    album_artwork = getattr(track, "album_artwork", None)
    duration_ms = getattr(track, "duration_ms", None)
    spotify_track_id = (
        getattr(track, "spotify_id", None)
        or getattr(track, "spotify_track_id", None)
    )

    track_name = getattr(track, "track_name", None) or getattr(track, "title", None)
    artist_name = getattr(artist, "name", None) or getattr(
        artist, "display_name", None
    )

    return {
        "rank": rank,
        # names the frontend expects (trackSequenceLoader / normalizeTrack)
        "trackName": track_name,
        "track_name": track_name,
        "artistName": artist_name,
        "artist_name": artist_name,
        "albumArtwork": album_artwork,
        "album_artwork": album_artwork,
        "durationMs": duration_ms,
        "duration_ms": duration_ms,
        "spotifyTrackId": spotify_track_id,
        "spotify_id": spotify_track_id,
        "track_spotify_id": spotify_track_id,
        # narration fields can be added later if you want
        "intro": None,
        "detail": None,
        "artistDescription": None,
    }


# -------------------------------------------------------------------
# ❶ DECADE + GENRE LOADER
#     /supabase/load-decade-genre-data
# -------------------------------------------------------------------
@router.get("/load-decade-genre-data")
def load_decade_genre_data(
    decade: str = Query(...),
    genre: str = Query(...),
    tts_language: str = Query("en"),
    session: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return ranked tracks for a given (decade, genre) combo.

    Matches the DecadeGenreResponse shape expected by:
      src/lib/api/supabaseLoader.ts
      src/lib/helpers/trackSequenceLoader.ts
    """
    logger.info("🎧 load_decade_genre_data decade=%s genre=%s", decade, genre)

    stmt = (
        select(TrackRanking, Track, Artist)
        .join(Track, TrackRanking.track_id == Track.id)
        .join(Artist, Track.artist_id == Artist.id)
        .where(TrackRanking.decade == decade)
        .where(TrackRanking.genre == genre)
        .order_by(TrackRanking.rank)
    )

    results = session.exec(stmt).all()

    rows: List[Dict[str, Any]] = []
    for tr, track, artist in results:
        rows.append(_safe_track_payload(tr.rank, track, artist))

    return {"rows": rows}


# -------------------------------------------------------------------
# ❷ COLLECTION LOADER
#     /supabase/load-collection-data/{slug}
# -------------------------------------------------------------------
@router.get("/load-collection-data/{slug}")
def load_collection_data(
    slug: str,
    tts_language: str = Query("en"),
    session: Session = Depends(get_db),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return ranked tracks for a given collection slug.

    Matches CollectionResponse shape expected by the frontend.
    """
    logger.info("🎧 load_collection_data slug=%s", slug)

    stmt = (
        select(CollectionTrackRanking, Track, Artist, Collection)
        .join(Track, CollectionTrackRanking.track_id == Track.id)
        .join(Artist, Track.artist_id == Artist.id)
        .join(Collection, CollectionTrackRanking.collection_id == Collection.id)
        .where(Collection.slug == slug)
        .order_by(CollectionTrackRanking.rank)
    )

    results = session.exec(stmt).all()

    rows: List[Dict[str, Any]] = []
    for ctr, track, artist, collection in results:
        rows.append(_safe_track_payload(ctr.rank, track, artist))

    return {"rows": rows}
