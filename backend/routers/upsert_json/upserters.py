from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from sqlmodel import Session, select
from sqlalchemy import and_, delete, func

from backend.models.dbmodels import Genre, Decade, DecadeGenre, Artist, ArtistGenre, Track, TrackRanking
from backend.utils.mode_utils import parse_mode_flag
from backend.utils.datetime_utils import parse_dt_utc

logger = logging.getLogger(__name__)

# ── Local error type to avoid FastAPI coupling
class SchemaError(Exception):
    """Raised when the DB schema shape is incompatible with expectations."""
    pass

# ── Shared string helpers (local)
def _norm(s: str | None) -> str:
    return (s or "").strip()

def _norm_key(s: str | None) -> str:
    return (s or "").strip().lower()

# ── 1) Ensure (Decade, Genre, DecadeGenre) exist
def ensure_combo(db: Session, decade_name: str, genre_name: str):
    genre_obj = db.exec(
        select(Genre).where(func.lower(Genre.genre_name) == genre_name.lower())
    ).first()
    if not genre_obj:
        genre_obj = Genre(genre_name=genre_name)
        db.add(genre_obj); db.flush()

    decade_obj = db.exec(
        select(Decade).where(func.lower(Decade.decade_name) == decade_name.lower())
    ).first()
    if not decade_obj:
        decade_obj = Decade(decade_name=decade_name)
        db.add(decade_obj); db.flush()

    decade_genre = db.exec(
        select(DecadeGenre).where(
            and_(DecadeGenre.decade_id == decade_obj.id, DecadeGenre.genre_id == genre_obj.id)
        )
    ).first()
    if not decade_genre:
        decade_genre = DecadeGenre(decade_id=decade_obj.id, genre_id=genre_obj.id)
        db.add(decade_genre); db.flush()

    return decade_obj, genre_obj, decade_genre

# ── 2) Upsert artists (+ ArtistGenre link)
def upsert_artists(
    *,
    db: Session,
    artists_in: List[Dict[str, Any]],
    genre_obj: Genre,
    preserve_artist_description: bool,
) -> Dict[str, int]:
    artist_map: Dict[str, int] = {}

    for a in artists_in:
        sid = _norm(a.get("spotify_artist_id"))
        name = _norm(a.get("artist_name") or a.get("artistName"))
        if not name:
            logger.warning("Skipping artist with no name")
            continue

        existing = None
        if sid:
            existing = db.exec(select(Artist).where(Artist.spotify_artist_id == sid)).first()
        if not existing:
            existing = db.exec(
                select(Artist).where(func.lower(Artist.artist_name) == name.lower())
            ).first()

        if existing:
            if (not preserve_artist_description) or not _norm(existing.artist_description):
                existing.artist_description = a.get("artist_description") or a.get("artistDescription")
            artist_id = existing.id
        else:
            new_artist = Artist(
                artist_name=name,
                spotify_artist_id=sid or None,
                artist_artwork=a.get("artist_artwork") or a.get("artistArtwork"),
                artist_description=a.get("artist_description") or a.get("artistDescription"),
                not_on_spotify=a.get("not_on_spotify", False),
            )
            db.add(new_artist); db.flush()
            artist_id = new_artist.id
            logger.info("Added artist: %s", name)

        key = _norm_key(sid) or _norm_key(name)
        artist_map[key] = artist_id

        # ensure ArtistGenre link
        if not db.exec(select(ArtistGenre).where(
            and_(ArtistGenre.artist_id == artist_id, ArtistGenre.genre_id == genre_obj.id)
        )).first():
            db.add(ArtistGenre(artist_id=artist_id, genre_id=genre_obj.id))

    return artist_map

# ── 3) Upsert tracks
def upsert_tracks(
    *,
    db: Session,
    tracks_in: List[Dict[str, Any]],
    artist_map: Dict[str, int],
    preserve_detail: bool,
) -> None:
    def _resolve_artist_id(artist_sid, artist_name):
        key = _norm_key(artist_sid) or _norm_key(artist_name)
        return artist_map.get(key)

    for t in tracks_in:
        sid        = _norm(t.get("spotify_track_id") or t.get("spotifyTrackId"))
        artist_sid = _norm(t.get("spotify_artist_id") or t.get("spotifyArtistId"))
        name       = _norm(t.get("track_name") or t.get("trackName"))
        if not name:
            logger.warning("Skipping track with no name"); continue

        artist_name = _norm(t.get("artist_name") or t.get("artistName"))
        artist_id   = _resolve_artist_id(artist_sid, artist_name)

        raw_flag    = t.get("mode_flag") or t.get("modeFlag")
        parsed_flag = parse_mode_flag(raw_flag)

        track_obj = None
        if sid:
            track_obj = db.exec(select(Track).where(Track.spotify_track_id == sid)).first()
        if not track_obj and artist_id:
            track_obj = db.exec(select(Track).where(
                and_(func.lower(Track.track_name) == name.lower(), Track.artist_id == artist_id)
            )).first()

        feat_sid  = _norm(t.get("featured_artist_sid") or t.get("featuredArtistSid"))
        feat_name = _norm(t.get("featured_artist_name") or t.get("featuredArtistName"))

        feat_id = None
        if feat_sid or feat_name:
            key = _norm_key(feat_sid) or _norm_key(feat_name)
            feat_id = artist_map.get(key)

        if track_obj:
            track_obj.track_name          = name
            track_obj.artist_display_name = t.get("artist_display_name") or t.get("artistDisplayName")
            track_obj.artist_id           = artist_id
            track_obj.featured_artist_id  = feat_id
            track_obj.spotify_track_id    = sid or track_obj.spotify_track_id
            track_obj.duration_ms         = t.get("duration_ms") or t.get("durationMs")
            track_obj.popularity          = t.get("popularity")
            track_obj.album_artwork       = t.get("album_artwork") or t.get("albumArtwork")
            track_obj.year_released       = t.get("year_released") or t.get("yearReleased")
            track_obj.is_explicit         = t.get("is_explicit") or t.get("isExplicit")
            track_obj.created_at          = parse_dt_utc(t.get("created_at") or t.get("createdAt"))
            track_obj.album_name          = t.get("album_name") or t.get("albumName")
            mf_val = getattr(parsed_flag, "value", parsed_flag)
            if mf_val:
                track_obj.mode_flag = mf_val
            if (not preserve_detail) or not _norm(track_obj.detail):
                track_obj.detail = t.get("detail")
        else:
            db.add(Track(
                track_name=name,
                artist_display_name=t.get("artist_display_name") or t.get("artistDisplayName"),
                artist_id=artist_id,
                featured_artist_id=feat_id,
                spotify_track_id=sid or None,
                duration_ms=t.get("duration_ms") or t.get("durationMs"),
                popularity=t.get("popularity"),
                album_artwork=t.get("album_artwork") or t.get("albumArtwork"),
                year_released=t.get("year_released") or t.get("yearReleased"),
                is_explicit=t.get("is_explicit") or t.get("isExplicit"),
                created_at=parse_dt_utc(t.get("created_at") or t.get("createdAt")),
                detail=t.get("detail"),
                album_name=t.get("album_name") or t.get("albumName"),
                mode_flag=(getattr(parsed_flag, "value", parsed_flag) or None),
            ))
            db.flush()
            logger.info("Added track: %s", name)

# ── 4) Upsert rankings
@dataclass
class RankingResult:
    upserted: int
    skipped: int
    dupes: int

def upsert_rankings(
    *,
    db: Session,
    rankings_in: List[Dict[str, Any]],
    decade_genre: DecadeGenre,
    tracklist_id: int,
    replace_rankings: bool,
    preserve_intro_text: bool,
    artist_map: Dict[str, int],
    genre_obj: Genre,
) -> RankingResult:
    # Which attribute does TrackRanking use in this schema?
    RANK_ATTR = "rank" if hasattr(TrackRanking, "rank") else ("ranking" if hasattr(TrackRanking, "ranking") else None)
    if not RANK_ATTR:
        # <-- decoupled from FastAPI
        raise SchemaError("TrackRanking model has neither 'rank' nor 'ranking' attribute")

    if replace_rankings:
        res = db.exec(
            delete(TrackRanking).where(
                (TrackRanking.decade_genre_id == decade_genre.id) &
                (TrackRanking.tracklist_id == tracklist_id)
            )
        )
        try:
            logger.info(
                "Deleted %s existing rankings for combo=%s tracklist_id=%s",
                getattr(res, "rowcount", "?"), decade_genre.id, tracklist_id
            )
        except Exception:
            pass

    if not isinstance(rankings_in, list):
        logger.warning("Expected 'track_ranking' to be a list, got %s; skipping rankings.", type(rankings_in).__name__)
        rankings_in = []

    upserted = 0
    skipped = 0
    dupes = 0
    logger.info("Processing %d ranking rows (RANK_ATTR=%s)", len(rankings_in), RANK_ATTR)

    pending_by_tid: dict[int, dict] = {}

    with db.no_autoflush:
        for r in rankings_in:
            # rank parsing
            rank_raw = r.get("rank", r.get("ranking"))
            try:
                rank_val = int(rank_raw) if rank_raw is not None and str(rank_raw).strip() != "" else None
            except (TypeError, ValueError):
                logger.warning("Skipping ranking with non-integer rank: %r", rank_raw)
                skipped += 1
                continue
            if rank_val is None:
                logger.warning("Skipping ranking with missing 'rank': %r", r)
                skipped += 1
                continue

            spotify_tid = _norm(r.get("track_id") or r.get("spotify_track_id") or r.get("spotifyTrackId"))
            created_at = parse_dt_utc(r.get("created_at") or r.get("createdAt"))
            intro_text = _norm(r.get("intro") or r.get("intro_text"))

            # Resolve/create track similar to old logic
            track_obj = None
            if spotify_tid:
                track_obj = db.exec(select(Track).where(Track.spotify_track_id == spotify_tid)).first()

            if not track_obj:
                tname = _norm(r.get("track_name") or r.get("trackName"))
                aname = _norm(r.get("artist_name") or r.get("artistName"))
                artist_id = artist_map.get(_norm_key(aname))

                # create missing artist on the fly if allowed
                if not artist_id and aname:
                    new_artist = Artist(artist_name=aname)
                    db.add(new_artist); db.flush()
                    artist_id = new_artist.id
                    db.add(ArtistGenre(artist_id=artist_id, genre_id=genre_obj.id))
                    artist_map[_norm_key(aname)] = artist_id

                if tname and artist_id:
                    track_obj = db.exec(select(Track).where(
                        and_(func.lower(Track.track_name) == tname.lower(), Track.artist_id == artist_id)
                    )).first()

                # name-only fallback if unique
                if not track_obj and tname:
                    candidates = db.exec(
                        select(Track).where(func.lower(Track.track_name) == tname.lower())
                    ).all()
                    if len(candidates) == 1:
                        track_obj = candidates[0]
                    elif len(candidates) > 1:
                        logger.warning("Ambiguous track name '%s' across artists; skipping name-only match.", tname)

                # if still missing and we have enough info, create track
                if not track_obj and (spotify_tid or (tname and artist_id)):
                    track_obj = Track(
                        track_name=tname or "Unknown",
                        artist_id=artist_id,
                        spotify_track_id=spotify_tid or None
                    )
                    db.add(track_obj); db.flush()

            if not track_obj:
                logger.warning("Skipping ranking; track not found/created: %s", r)
                skipped += 1
                continue

            tid = track_obj.id

            if replace_rankings:
                # Dedupe within this import run: keep lowest rank for same track
                existing = pending_by_tid.get(tid)
                if existing:
                    dupes += 1
                    current_best = existing[RANK_ATTR]
                    if rank_val < current_best:
                        existing[RANK_ATTR] = rank_val
                        existing["intro"] = intro_text if intro_text else existing.get("intro")
                        existing["created_at"] = created_at or existing.get("created_at")
                    else:
                        if (not existing.get("intro")) and intro_text:
                            existing["intro"] = intro_text
                        if (not existing.get("created_at")) and created_at:
                            existing["created_at"] = created_at
                    continue

                pending_by_tid[tid] = {
                    "track_id": tid,
                    "decade_genre_id": decade_genre.id,
                    "tracklist_id": tracklist_id,
                    "intro": intro_text,
                    "created_at": created_at,
                    RANK_ATTR: rank_val,
                }
            else:
                # upsert (unique on track_id, decade_genre_id, tracklist_id)
                existing = db.exec(select(TrackRanking).where(
                    and_(
                        TrackRanking.track_id == tid,
                        TrackRanking.decade_genre_id == decade_genre.id,
                        TrackRanking.tracklist_id == tracklist_id,
                    )
                )).first()
                if existing:
                    setattr(existing, RANK_ATTR, rank_val)
                    existing.created_at = created_at
                    if preserve_intro_text:
                        if not _norm(existing.intro):
                            existing.intro = intro_text
                    else:
                        existing.intro = intro_text
                else:
                    db.add(TrackRanking(
                        track_id=tid,
                        decade_genre_id=decade_genre.id,
                        tracklist_id=tracklist_id,
                        intro=intro_text,
                        created_at=created_at,
                        **{RANK_ATTR: rank_val},
                    ))
                upserted += 1

    # After loop: actually add the deduped rows (replace_rankings=True)
    if replace_rankings and pending_by_tid:
        for row in pending_by_tid.values():
            db.add(TrackRanking(**row))
            upserted += 1

    return RankingResult(upserted=upserted, skipped=skipped, dupes=dupes)
