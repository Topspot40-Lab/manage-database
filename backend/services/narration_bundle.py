# backend/services/narration_bundle.py
from __future__ import annotations

from typing import Optional, Tuple, Dict, Any
from fastapi import Request
import logging
from sqlmodel import Session, select

from backend.models.dbmodels import TrackRanking, Track, Artist
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.services.supabase_signer import sign_url
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename,
    build_collection_intro_filename,  # ✅
)
from backend.services.db_queries import get_decade_genre

logger = logging.getLogger(__name__)

def _signed(bucket: Optional[str], key: Optional[str], expires: int) -> Optional[str]:
    if not bucket or not key:
        return None
    try:
        return sign_url(bucket, key, expires)
    except Exception as e:
        logger.warning("sign_url failed: %s", e)
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
    intros: list[str] = []
    detail_url: Optional[str] = None
    artist_url: Optional[str] = None

    # Intro(s)
    if want_intro_key:
        intro_bucket, intro_key = want_intro_key
        intro_url = _signed(intro_bucket, intro_key, expires)
        if intro_url:
            intros.append(intro_url)

    # Detail narration (per-track)
    if use_detail:
        df = build_detail_filename(track.spotify_track_id)
        if df:
            detail_url = _signed(bucket_for(lang, "detail"), key_for("detail", df), expires)

    # Artist narration (per-artist)
    if use_artist and artist and getattr(artist, "spotify_artist_id", None):
        af = build_artist_filename(artist.spotify_artist_id)
        if af:
            artist_url = _signed(bucket_for(lang, "artist"), key_for("artist", af), expires)

    return {
        "rank": rank,
        "spotify_track_id": track.spotify_track_id,
        "intros": intros,
        "detail": detail_url,
        "artist": artist_url,
        "track_name": track.track_name,
        "artist_name": artist.artist_name if artist else None,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Decade/Genre version
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
    request: Request,  # parity with callers (unused here)
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return None, {"error": f"No DecadeGenre for {decade}/{genre}"}

    rk = db.exec(select(TrackRanking).where(
        TrackRanking.decade_genre_id == dg.id,
        TrackRanking.ranking == rank
    )).first()
    if not rk:
        return None, {"error": f"No ranking #{rank} in {decade}/{genre}"}

    track: Track = db.get(Track, rk.track_id)
    artist: Optional[Artist] = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return None, {"error": "Track or Artist not found"}

    want_intro_key: Optional[Tuple[str, str]] = None
    if use_intro:
        intro_fn = build_intro_filename(decade, genre, rank)
        want_intro_key = (bucket_for(lang, "intro"), key_for("intro", intro_fn))

    payload = _bundle_from_track(
        rank=rank, lang=lang, track=track, artist=artist,
        want_intro_key=want_intro_key,
        use_detail=use_detail, use_artist=use_artist,
        expires=expires,
    )
    return payload, None

# ─────────────────────────────────────────────────────────────────────────────
# Collection version (supports per-collection intros)
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
    request: Request,               # parity with callers (unused here)
    collection_slug: Optional[str] = None,  # pass this to avoid an extra DB fetch
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    ctr = db.exec(select(CollectionTrackRanking).where(
        CollectionTrackRanking.collection_id == collection_id,
        CollectionTrackRanking.ranking == rank
    )).first()
    if not ctr:
        return None, {"error": f"No ranking #{rank} in collection {collection_id}"}

    track: Track = db.get(Track, ctr.track_id)
    artist: Optional[Artist] = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return None, {"error": "Track or Artist not found"}

    want_intro_key: Optional[Tuple[str, str]] = None
    if use_intro:
        if not collection_slug:
            coll = db.get(Collection, collection_id)
            collection_slug = coll.slug if coll else None
        if collection_slug:
            intro_fn = build_collection_intro_filename(collection_slug, rank)  # slug_{rank:02}.mp3
            want_intro_key = (
                bucket_for(lang, "collections_intro"),       # ✅ plural key
                key_for("collections_intro", intro_fn),      # ✅ plural key
            )

    payload = _bundle_from_track(
        rank=rank, lang=lang, track=track, artist=artist,
        want_intro_key=want_intro_key,
        use_detail=use_detail, use_artist=use_artist,
        expires=expires,
    )
    return payload, None

__all__ = ["urls_for_rank_dg", "urls_for_rank_collection"]
