from fastapi import APIRouter, HTTPException, Path, Depends, Query
from sqlmodel import Session, select
import logging, sqlalchemy
from sqlalchemy import and_, delete, func
from datetime import datetime

from backend.utils.mode_utils import parse_mode_flag
from backend.database import get_db
from backend.models import Genre, Decade, DecadeGenre, Artist, ArtistGenre, Track, TrackRanking
from backend.utils.json_helpers import load_full_json_file
from backend.services.supabase_storage import delete_intro_mp3_files_for_combo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["json-upsert"])

def _norm(s: str | None) -> str:
    return (s or "").strip()

def _norm_key(s: str | None) -> str:
    # key for maps: strip + lowercase
    return (s or "").strip().lower()

def _parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        # tolerant ISO parse; extend if you have other formats
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except Exception:
        return None

@router.post("/upsert-json-and-reset/{decade}/{genre}")
async def upsert_json_and_reset(
    decade: str = Path(..., description="e.g., 1980s"),
    genre: str  = Path(..., description="e.g., rock"),
    replace_rankings: bool = Query(True,  description="Delete all existing rankings for this combo then insert from JSON"),
    reset_intro_mp3s: bool = Query(True,  description="Delete intro MP3s in storage for this combo before changes"),
    preserve_intro_text: bool = Query(False, description="Keep existing TrackRanking.intro when present"),
    preserve_detail: bool = Query(True),
    preserve_artist_description: bool = Query(True),
    tracklist_id: int = Query(1),
    dry_run: bool = Query(False),
    store_json_copy: bool = Query(False, description="Upload JSON blob to Storage for auditing (optional)"),
    db: Session = Depends(get_db),
):
    """Rebuild a (decade, genre) from local JSON. Idempotent-ish: safe to re-run."""

    try:
        if db.bind is not None:
            logger.info("Schema: %s", sqlalchemy.inspect(db.bind).default_schema_name)
    except Exception:
        pass

    filename = f"{decade}_{genre}_en.json"

    # 1) Load JSON
    try:
        data = load_full_json_file(decade, filename)
        logger.info("Loaded JSON: %s", filename)
    except FileNotFoundError:
        raise HTTPException(404, f"JSON file not found: {filename}")
    except Exception as e:
        raise HTTPException(500, f"Read error: {e}")

    if isinstance(data, list):
        data = {"track_ranking": data}

    decade_name = _norm(data.get("category")) or decade
    genre_name  = _norm(data.get("genre")) or genre

    artists_in   = data.get("artist", []) or []
    if isinstance(artists_in, dict):
        artists_in = [artists_in]
    tracks_in    = data.get("track", []) or []
    rankings_in  = data.get("track_ranking", []) or []

    if dry_run:
        return {
            "status": "dry_run",
            "decade": decade_name,
            "genre": genre_name,
            "would_upsert": {
                "artists": len(artists_in),
                "tracks": len(tracks_in),
                "rankings": len(rankings_in),
            },
            "would_reset_intro_mp3s": bool(reset_intro_mp3s),
            "replace_rankings": bool(replace_rankings),
            "tracklist_id": tracklist_id,
            "note": "No DB writes or storage changes performed.",
        }

    # 2–6) Do the whole thing in one transaction
    try:
        with db.begin():
            # 2) Resolve/create Decade/Genre/DecadeGenre
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

            # 4) Upsert Artists (+ ArtistGenre)
            artist_map: dict[str, int] = {}
            for a in artists_in:
                sid  = _norm(a.get("spotify_artist_id"))
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

            # 5) Upsert Tracks
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
                feat_id   = _resolve_artist_id(feat_sid, feat_name)

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
                    track_obj.created_at          = t.get("created_at") or t.get("createdAt")
                    track_obj.album_name          = t.get("album_name") or t.get("albumName")
                    track_obj.mode_flag           = parsed_flag.value if parsed_flag else track_obj.mode_flag
                    if (not preserve_detail) or not _norm(track_obj.detail):
                        track_obj.detail = t.get("detail")
                else:
                    track_obj = Track(
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
                        created_at=t.get("created_at") or t.get("createdAt"),
                        detail=t.get("detail"),
                        album_name=t.get("album_name") or t.get("albumName"),
                        mode_flag=(parsed_flag.value if parsed_flag else None),
                    )
                    db.add(track_obj); db.flush()
                    logger.info("Added track: %s", name)

            # 6) Rankings
            create_missing_from_rankings = True

            if replace_rankings:
                db.exec(
                    delete(TrackRanking).where(
                        and_(
                            TrackRanking.decade_genre_id == decade_genre.id,
                            TrackRanking.tracklist_id == tracklist_id,
                        )
                    )
                )

            upserted = 0
            for r in rankings_in:
                spotify_tid = _norm(r.get("track_id") or r.get("spotify_track_id") or r.get("spotifyTrackId"))
                rank_val    = r.get("rank")
                created_at  = _parse_dt(r.get("created_at") or r.get("createdAt"))
                intro_text  = _norm(r.get("intro") or r.get("intro_text"))

                # resolve track
                track_obj = None
                if spotify_tid:
                    track_obj = db.exec(select(Track).where(Track.spotify_track_id == spotify_tid)).first()

                if not track_obj:
                    tname = _norm(r.get("track_name") or r.get("trackName"))
                    aname = _norm(r.get("artist_name") or r.get("artistName"))
                    artist_id = artist_map.get(_norm_key(aname))
                    if not artist_id and create_missing_from_rankings and aname:
                        new_artist = Artist(artist_name=aname)
                        db.add(new_artist); db.flush()
                        artist_id = new_artist.id
                        db.add(ArtistGenre(artist_id=artist_id, genre_id=genre_obj.id))
                        artist_map[_norm_key(aname)] = artist_id
                    if tname and artist_id:
                        track_obj = db.exec(select(Track).where(
                            and_(func.lower(Track.track_name) == tname.lower(), Track.artist_id == artist_id)
                        )).first()
                    if not track_obj and create_missing_from_rankings and (spotify_tid or (tname and artist_id)):
                        track_obj = Track(track_name=tname or "Unknown", artist_id=artist_id, spotify_track_id=spotify_tid or None)
                        db.add(track_obj); db.flush()

                if not track_obj:
                    logger.warning("Skipping ranking; track not found/created: %s", r)
                    continue

                if replace_rankings:
                    db.add(TrackRanking(
                        track_id=track_obj.id,
                        decade_genre_id=decade_genre.id,
                        tracklist_id=tracklist_id,
                        ranking=rank_val,
                        intro=intro_text,
                        created_at=created_at,
                    ))
                else:
                    existing = db.exec(select(TrackRanking).where(
                        and_(
                            TrackRanking.track_id == track_obj.id,
                            TrackRanking.decade_genre_id == decade_genre.id,
                            TrackRanking.tracklist_id == tracklist_id,
                        )
                    )).first()
                    if existing:
                        existing.ranking = rank_val
                        existing.created_at = created_at
                        if preserve_intro_text:
                            if not _norm(existing.intro):
                                existing.intro = intro_text
                        else:
                            existing.intro = intro_text
                    else:
                        db.add(TrackRanking(
                            track_id=track_obj.id,
                            decade_genre_id=decade_genre.id,
                            tracklist_id=tracklist_id,
                            ranking=rank_val,
                            intro=intro_text,
                            created_at=created_at,
                        ))
                upserted += 1

        # transaction exits here (commit)

    except HTTPException:
        raise
    except Exception as e:
        # .begin() auto-rolls back on exception
        raise HTTPException(500, f"Upsert failed: {e}")

    # 7) Storage cleanup (non-fatal if it fails)
    if reset_intro_mp3s:
        try:
            report = delete_intro_mp3_files_for_combo(
                decade_name, genre_name,
                languages=("en",),  # extend if you keep es/pt files side-by-side
                dry_run=False
            )
            logger.info("Intro MP3 cleanup report: %s", report)
        except Exception as e:
            logger.error("Storage cleanup failed: %s", e)

    if store_json_copy:
        logger.info("JSON storage upload requested; implement helper when ready.")

    return {
        "status": "success",
        "decade": decade_name,
        "genre": genre_name,
        "replace_rankings": replace_rankings,
        "reset_intro_mp3s": reset_intro_mp3s,
        "tracklist_id": tracklist_id,
        "note": "Upsert completed; intro MP3s cleared if requested. Proceed to regenerate TTS.",
    }
