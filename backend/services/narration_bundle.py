# backend/services/narration_bundle.py
from __future__ import annotations

from typing import Optional, Tuple, Dict, Any
from fastapi import Request
import logging
from sqlmodel import Session, select

from backend.models.dbmodels import TrackRanking, Track, Artist
from backend.models.collection_models import CollectionTrackRanking
from backend.services.supabase_signer import sign_url
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename,
)
from backend.services.db_queries import get_decade_genre

logger = logging.getLogger(__name__)


def _signed(bucket: Optional[str], key: Optional[str], expires: int) -> Optional[str]:
    if not bucket or not key:
        return None
    try:
        return sign_url(bucket, key, expires)
    except Exception as e:
        logger.warning("sign_url failed for bucket=%r key=%r: %s", bucket, key, e)
        return None


def _bundle_from_track(
    *,
    rank: int,
    lang: str,
    track: Track,
    artist: Optional[Artist],
    want_intro_key: Optional[Tuple[str, str]],  # (bucket, key) or None
    use_detail: bool,
    use_artist: bool,
    expires: int,
) -> Dict[str, Any]:
    """
    Build a client bundle with (optional) intro/detail/artist narration URLs
    and minimal track/artist metadata. Safe to call even if some assets are missing.
    """
    intros: list[str] = []
    detail_url: Optional[str] = None
    artist_url: Optional[str] = None

    # Intro(s)
    if want_intro_key:
        intro_bucket, intro_key = want_intro_key
        intro_url = _signed(intro_bucket, intro_key, expires)
        if intro_url:
            intros.append(intro_url)

    # Detail narration (per-track) — only if we actually have a spotify id
    if use_detail and getattr(track, "spotify_track_id", None):
        detail_fn = build_detail_filename(track.spotify_track_id)
        if detail_fn:
            detail_key = key_for("detail", detail_fn)
            detail_bucket = bucket_for(lang, "detail")
            detail_url = _signed(detail_bucket, detail_key, expires)

    # Artist narration (per-artist)
    if use_artist and artist and getattr(artist, "spotify_artist_id", None):
        artist_fn = build_artist_filename(artist.spotify_artist_id)
        if artist_fn:
            artist_key = key_for("artist", artist_fn)
            artist_bucket = bucket_for(lang, "artist")
            artist_url = _signed(artist_bucket, artist_key, expires)

    return {
        "rank": rank,
        "spotify_track_id": getattr(track, "spotify_track_id", None),
        "intros": intros,
        "detail": detail_url,
        "artist": artist_url,
        "track_name": getattr(track, "track_name", None),
        "artist_name": getattr(artist, "artist_name", None) if artist else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Decade/Genre version (matches your current inline helper)
# ─────────────────────────────────────────────────────────────────────────────
def urls_for_rank_dg(
    db: Session,
    lang: str,
    decade: str,
    genre: str,
    rank: int,
    *,
    use_intro: bool,
    use_detail: bool,
    use_artist: bool,
    expires: int,
    request: Request,  # kept for signature parity (not used here)
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (payload, error) for a Decade/Genre ranking row."""
    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return None, {"error": f"No DecadeGenre for {decade}/{genre}"}

    rk = db.exec(
        select(TrackRanking).where(
            TrackRanking.decade_genre_id == dg.id,
            TrackRanking.ranking == rank
        )
    ).first()
    if not rk:
        return None, {"error": f"No ranking #{rank} in {decade}/{genre}"}

    track: Optional[Track] = db.get(Track, rk.track_id)
    artist: Optional[Artist] = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        logger.warning(
            "DG bundle: missing track/artist (dg_id=%s, rank=%s, track_id=%s)",
            dg.id, rank, getattr(rk, "track_id", None)
        )
        return None, {"error": "Track or Artist not found"}

    want_intro_key: Optional[Tuple[str, str]] = None
    if use_intro:
        intro_fn = build_intro_filename(decade, genre, rank)
        intro_key = key_for("intro", intro_fn)
        intro_bucket = bucket_for(lang, "intro")
        want_intro_key = (intro_bucket, intro_key)

    payload = _bundle_from_track(
        rank=rank, lang=lang, track=track, artist=artist,
        want_intro_key=want_intro_key,
        use_detail=use_detail, use_artist=use_artist,
        expires=expires,
    )
    return payload, None


# ─────────────────────────────────────────────────────────────────────────────
# Collection version (no per-collection intro by default)
# Add your own intro filename logic if you render collection intros.
# ─────────────────────────────────────────────────────────────────────────────
def urls_for_rank_collection(
    db: Session,
    lang: str,
    collection_id: int,
    rank: int,
    *,
    use_intro: bool,
    use_detail: bool,
    use_artist: bool,
    expires: int,
    request: Request,  # kept for signature parity (not used here)
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (payload, error) for a Collection ranking row."""
    ctr = db.exec(
        select(CollectionTrackRanking).where(
            CollectionTrackRanking.collection_id == collection_id,
            CollectionTrackRanking.ranking == rank
        )
    ).first()
    if not ctr:
        return None, {"error": f"No ranking #{rank} in collection {collection_id}"}

    track: Optional[Track] = db.get(Track, ctr.track_id)
    artist: Optional[Artist] = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        logger.warning(
            "Collection bundle: missing track/artist (collection_id=%s, rank=%s, track_id=%s)",
            collection_id, rank, getattr(ctr, "track_id", None)
        )
        return None, {"error": "Track or Artist not found"}

    # If you have per-collection intro MP3s, compute a (bucket, key) pair here.
    want_intro_key: Optional[Tuple[str, str]] = None
    if use_intro:
        # Example placeholder (implement if/when you have collection intros):
        # intro_fn = build_collection_intro_filename(collection_id, rank)
        # want_intro_key = (bucket_for(lang, "intro"), key_for("intro", intro_fn))
        want_intro_key = None

    payload = _bundle_from_track(
        rank=rank, lang=lang, track=track, artist=artist,
        want_intro_key=want_intro_key,
        use_detail=use_detail, use_artist=use_artist,
        expires=expires,
    )
    return payload, None


__all__ = ["urls_for_rank_dg", "urls_for_rank_collection"]
