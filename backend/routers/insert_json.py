from fastapi import APIRouter, HTTPException, Path, Depends, Query
from sqlmodel import Session, select
import logging, sqlalchemy
from sqlalchemy import and_, delete

from backend.utils.mode_utils import  parse_mode_flag
from backend.database import get_db
from backend.models import Genre, Decade, DecadeGenre, Artist, ArtistGenre, Track, TrackRanking
from backend.utils.json_helpers import load_full_json_file
from backend.services.supabase_storage import delete_intro_mp3_files_for_combo
# from backend.services.supabase_storage import upload_json_to_storage  # <-- optional (see TODO)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["json-upsert"])


@router.post("/upsert-json-and-reset/{decade}/{genre}")
async def upsert_json_and_reset(
    decade: str = Path(..., description="e.g., 1980s"),
    genre: str = Path(..., description="e.g., rock"),
    # Behavior toggles
    replace_rankings: bool = Query(True, description="Delete all existing rankings for this combo then insert from JSON"),
    reset_intro_mp3s: bool = Query(True, description="Delete intro MP3s in storage for this combo before changes"),
    preserve_intro_text: bool = Query(False, description="If True, keep existing TrackRanking.intro text when present"),
    preserve_detail: bool = Query(True),
    preserve_artist_description: bool = Query(True),
    tracklist_id: int = Query(1),
    dry_run: bool = Query(False),
    # Optional: store the JSON you used into Supabase Storage for traceability
    store_json_copy: bool = Query(False, description="Upload JSON blob to Storage for auditing (optional)"),

    db: Session = Depends(get_db),
):
    """
    Rebuild a (decade, genre) from a local JSON file:
    - Upsert Genre/Decade/DecadeGenre, Artists (+ArtistGenre), and Tracks.
    - Optionally wipe existing TrackRanking rows for that combo and insert fresh.
    - Optionally delete storage intro MP3s so TTS can be regenerated.
    - Leaves existing rows in place when present; creates new when missing.
    """
    logger.info(f"Schema: {sqlalchemy.inspect(db.bind).default_schema_name}")
    filename = f"{decade}_{genre}_en.json"

    # -------------------------------------------------------
    # 1) Load & normalize JSON
    # -------------------------------------------------------
    try:
        data = load_full_json_file(decade, filename)  # your existing helper
        logger.info(f"Loaded JSON: {filename}")
    except FileNotFoundError:
        raise HTTPException(404, f"JSON file not found: {filename}")
    except Exception as e:
        raise HTTPException(500, f"Read error: {e}")

    # Accept both array or keyed objects
    # Expect keys: "artist", "track", "track_ranking"; tolerate array-only (treat as track_ranking)
    if isinstance(data, list):
        data = {"track_ranking": data}

    # Some older dumps had {"category": "...", "genre": "..."} for decade/genre
    decade_name = data.get("category") or decade
    genre_name = data.get("genre") or genre

    if isinstance(data.get("artist"), dict):
        logger.warning("Patching artist field from dict to list")
        data["artist"] = [data["artist"]]

    artists_in = data.get("artist", [])
    tracks_in = data.get("track", [])
    rankings_in = data.get("track_ranking", [])

    # After: artists_in = ..., tracks_in = ..., rankings_in = ...
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

    # -------------------------------------------------------
    # 2) Resolve or create Decade / Genre / DecadeGenre
    # -------------------------------------------------------
    try:
        genre_obj = db.exec(select(Genre).where(Genre.genre_name == genre_name)).first()
        if not genre_obj:
            genre_obj = Genre(genre_name=genre_name)
            db.add(genre_obj); db.commit(); db.refresh(genre_obj)

        decade_obj = db.exec(select(Decade).where(Decade.decade_name == decade_name)).first()
        if not decade_obj:
            decade_obj = Decade(decade_name=decade_name)
            db.add(decade_obj); db.commit(); db.refresh(decade_obj)

        decade_genre = db.exec(
            select(DecadeGenre).where(
                and_(DecadeGenre.decade_id == decade_obj.id, DecadeGenre.genre_id == genre_obj.id)
            )
        ).first()
        if not decade_genre:
            decade_genre = DecadeGenre(decade_id=decade_obj.id, genre_id=genre_obj.id)
            db.add(decade_genre); db.commit(); db.refresh(decade_genre)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed resolving decade/genre: {e}")

    # -------------------------------------------------------
    # 3) Storage cleanup – defer until DB succeeds; skip on dry_run
    # -------------------------------------------------------
    do_storage_cleanup = reset_intro_mp3s and not dry_run

    # -------------------------------------------------------
    # 4) Upsert Artists (+ ArtistGenre)
    # -------------------------------------------------------
    artist_map = {}  # key → artist_id (prefer spotify id, else name)
    try:
        for a in artists_in:
            sid = (a.get("spotify_artist_id") or "").strip() or None
            name = a.get("artist_name") or a.get("artistName")
            if not name:
                logger.warning("Skipping artist with no name"); continue
            name = name.strip()

            if sid:
                existing = db.exec(select(Artist).where(Artist.spotify_artist_id == sid)).first()
            else:
                existing = db.exec(select(Artist).where(Artist.artist_name == name)).first()

            if existing:
                # Update description if allowed / missing
                if (not preserve_artist_description) or (not existing.artist_description or not existing.artist_description.strip()):
                    existing.artist_description = a.get("artist_description") or a.get("artistDescription")
                artist_id = existing.id
            else:
                new_artist = Artist(
                    artist_name=name,
                    spotify_artist_id=sid,
                    artist_artwork=a.get("artist_artwork") or a.get("artistArtwork"),
                    artist_description=a.get("artist_description") or a.get("artistDescription"),
                    not_on_spotify=a.get("not_on_spotify", False),
                )
                db.add(new_artist); db.commit(); db.refresh(new_artist)
                artist_id = new_artist.id
                logger.info(f"Added artist: {name}")

            artist_map[sid or name] = artist_id

            # Ensure ArtistGenre link exists
            if not db.exec(select(ArtistGenre).where(
                ArtistGenre.artist_id == artist_id, ArtistGenre.genre_id == genre_obj.id
            )).first():
                db.add(ArtistGenre(artist_id=artist_id, genre_id=genre_obj.id))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Artist upsert failed: {e}")

    # -------------------------------------------------------
    # 5) Upsert Tracks
    # -------------------------------------------------------
    track_map = {}  # (track_name, artist_id) → track_id
    try:
        for t in tracks_in:
            sid = (t.get("spotify_track_id") or t.get("spotifyTrackId") or "").strip() or None
            artist_sid = (t.get("spotify_artist_id") or t.get("spotifyArtistId") or "").strip() or None
            name = t.get("track_name") or t.get("trackName")
            if not name:
                logger.warning("Skipping track with no name"); continue
            name = name.strip()
            artist_key = artist_sid or (t.get("artist_name") or t.get("artistName") or "").strip()
            artist_id = artist_map.get(artist_key)

            raw_flag = t.get("mode_flag") or t.get("modeFlag")
            parsed_flag = parse_mode_flag(raw_flag)

            # Find existing by spotify id if present, else by (name, artist_id)
            with db.no_autoflush:
                track_obj = db.exec(select(Track).where(Track.spotify_track_id == sid)).first() if sid else \
                            db.exec(select(Track).where(and_(Track.track_name == name, Track.artist_id == artist_id))).first()

            # Featured artist support
            feat_sid = (t.get("featured_artist_sid") or t.get("featuredArtistSid") or "").strip() or None
            feat_name = (t.get("featured_artist_name") or t.get("featuredArtistName") or "").strip() or None
            featured_artist_id = artist_map.get(feat_sid or feat_name)

            if track_obj:
                # Update core fields and detail if allowed/missing
                track_obj.track_name = name
                track_obj.artist_display_name = t.get("artist_display_name") or t.get("artistDisplayName")
                track_obj.artist_id = artist_id
                track_obj.featured_artist_id = featured_artist_id
                track_obj.spotify_track_id = sid or track_obj.spotify_track_id
                track_obj.duration_ms = t.get("duration_ms") or t.get("durationMs")
                track_obj.popularity = t.get("popularity")
                track_obj.album_artwork = t.get("album_artwork") or t.get("albumArtwork")
                track_obj.year_released = t.get("year_released") or t.get("yearReleased")
                track_obj.is_explicit = t.get("is_explicit") or t.get("isExplicit")
                track_obj.created_at = t.get("created_at") or t.get("createdAt")
                track_obj.album_name = t.get("album_name") or t.get("albumName")
                track_obj.mode_flag = parsed_flag.value if parsed_flag else track_obj.mode_flag
                # Detail text
                det = t.get("detail")
                if (not preserve_detail) or (not track_obj.detail or not track_obj.detail.strip()):
                    track_obj.detail = det
            else:
                track_obj = Track(
                    track_name=name,
                    artist_display_name=t.get("artist_display_name") or t.get("artistDisplayName"),
                    artist_id=artist_id,
                    featured_artist_id=featured_artist_id,
                    spotify_track_id=sid,
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
                db.add(track_obj); db.commit(); db.refresh(track_obj)
                logger.info(f"Added track: {name}")

            track_map[(track_obj.track_name, artist_id)] = track_obj.id

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Track upsert failed: {e}")

    # -------------------------------------------------------
    # 6) Rankings: replace (delete+insert) OR upsert row-by-row (atomic)
    # -------------------------------------------------------

    def _parse_dt(val):
        return val  # TODO: parse if your model requires datetime

    create_missing_from_rankings: bool = True  # make this a Query param if you want

    try:
        if dry_run:
            # Just simulate counts
            upserted = sum(1 for _ in rankings_in)
        else:
            # One transaction for the whole operation when writing
            with db.begin():
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
                    spotify_tid = (r.get("track_id") or r.get("spotify_track_id") or r.get(
                        "spotifyTrackId") or "").strip() or None
                    rank_val = r.get("rank")
                    created_at = _parse_dt(r.get("created_at") or r.get("createdAt"))
                    intro_payload = (r.get("intro") or r.get("intro_text") or "").strip()

                    # Resolve (or optionally create) Track
                    track_obj = None
                    if spotify_tid:
                        track_obj = db.exec(select(Track).where(Track.spotify_track_id == spotify_tid)).first()

                    if not track_obj:
                        tname = (r.get("track_name") or r.get("trackName") or "").strip()
                        aname = (r.get("artist_name") or r.get("artistName") or "").strip()
                        artist_id = artist_map.get(aname)

                        if not artist_id and create_missing_from_rankings and aname:
                            # create artist on the fly
                            new_artist = Artist(artist_name=aname)
                            db.add(new_artist)
                            db.flush()
                            db.refresh(new_artist)
                            artist_id = new_artist.id
                            # link to this genre
                            db.add(ArtistGenre(artist_id=artist_id, genre_id=genre_obj.id))
                            # ✅ keep the map in sync to avoid duplicate artists on later rows
                            artist_map[aname] = artist_id

                        if tname and artist_id:
                            track_obj = db.exec(
                                select(Track).where(and_(Track.track_name == tname, Track.artist_id == artist_id))
                            ).first()

                        if not track_obj and create_missing_from_rankings and (spotify_tid or (tname and artist_id)):
                            # Create a minimal track stub
                            track_obj = Track(
                                track_name=tname or "Unknown",
                                artist_id=artist_id,
                                spotify_track_id=spotify_tid,
                            )
                            db.add(track_obj)
                            db.flush()
                            db.refresh(track_obj)

                    if not track_obj:
                        logger.warning(f"Skipping ranking; track not found and not created for payload: {r}")
                        continue

                    if replace_rankings:
                        # rows were wiped; insert fresh
                        db.add(TrackRanking(
                            track_id=track_obj.id,
                            decade_genre_id=decade_genre.id,
                            tracklist_id=tracklist_id,
                            ranking=rank_val,
                            intro=intro_payload,
                            created_at=created_at
                        ))
                    else:
                        # upsert per row
                        existing = db.exec(select(TrackRanking).where(
                            and_(
                                TrackRanking.track_id == track_obj.id,
                                TrackRanking.decade_genre_id == decade_genre.id,
                                TrackRanking.tracklist_id == tracklist_id
                            )
                        )).first()

                        if existing:
                            existing.ranking = rank_val
                            existing.created_at = created_at
                            if preserve_intro_text:
                                if not (existing.intro and existing.intro.strip()):
                                    existing.intro = intro_payload
                            else:
                                existing.intro = intro_payload
                        else:
                            db.add(TrackRanking(
                                track_id=track_obj.id,
                                decade_genre_id=decade_genre.id,
                                tracklist_id=tracklist_id,
                                ranking=rank_val,
                                intro=intro_payload,
                                created_at=created_at
                            ))

                    upserted += 1
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Ranking upsert failed: {e}")

    # -------------------------------------------------------
    # 7) Optional: delete intro MP3s now that DB is consistent
    # -------------------------------------------------------
    if do_storage_cleanup:
        try:
            report = delete_intro_mp3_files_for_combo(
                decade_name, genre_name,
                languages=("en",),  # or ("en","es","pt-BR") if you store those
                dry_run=False  # actually delete
            )
            logger.info(f"Intro MP3 cleanup report: {report}")
        except Exception as e:
            logger.error(f"Storage cleanup failed: {e}")  # non-fatal

    if store_json_copy:
        try:
            # TODO: implement upload_json_to_storage(bucket, path, data_bytes)
            # path = f"json/{decade_name}/{genre_name}/source_{decade_name}_{genre_name}_en.json"
            # await upload_json_to_storage('topspot-json', path, json.dumps(data, ensure_ascii=False).encode('utf-8'))
            logger.info("JSON storage upload requested, implement helper as needed.")
        except Exception as e:
            logger.error(f"JSON storage upload failed: {e} (non-fatal)")

    return {
        "status": "success",
        "decade": decade_name,
        "genre": genre_name,
        "decade_genre_id": decade_genre.id,
        "replace_rankings": replace_rankings,
        "reset_intro_mp3s": reset_intro_mp3s,
        "tracklist_id": tracklist_id,
        "note": "Upsert completed; intro MP3s cleared if requested. Proceed to regenerate TTS."
    }

