from fastapi import APIRouter, HTTPException, Path, Depends
from sqlmodel import Session, select
import logging
import sqlalchemy
from backend.utils.mode_utils import ModeFlag
from sqlalchemy import and_
from fastapi import Query


from backend.utils.mode_utils import parse_mode_flag
from backend.database import get_db
from backend.models import Genre, Decade, DecadeGenre, Artist, ArtistGenre, Track, TrackRanking
from backend.utils.json_helpers import load_full_json_file
from backend.services.supabase_storage import delete_intro_mp3_files_for_combo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["json-insert"])
@router.post("/insert-json-to-db/{decade}/{genre}")
async def insert_json_to_db(
    decade: str = Path(...),
    genre: str = Path(...),
    preserve_intro: bool = Query(True),
    preserve_detail: bool = Query(True),
    preserve_artist_description: bool = Query(True),
    force: bool = Query(False),

    db: Session = Depends(get_db)
):
    logger.info(f"Connected to DB and using schema: {sqlalchemy.inspect(db.bind).default_schema_name}")

    try:
        filename = f"{decade}_{genre}_en.json"
        data = load_full_json_file(decade, filename)
        logger.info(f"Loaded JSON file: {filename}")

        if isinstance(data.get("artist"), dict):
            logger.warning("⚠️ Patching artist field from dict to list")
            data["artist"] = [data["artist"]]

    except FileNotFoundError:
        logger.error("JSON file not found")
        raise HTTPException(404, "JSON file not found")
    except Exception as e:
        logger.error(f"Error reading JSON: {e}")
        raise HTTPException(500, f"Read error: {e}")

    try:
        genre_name = data["genre"]
        decade_name = data["category"]

        # 🚨 Safety check to abort if DecadeGenre already exists
        existing_genre = db.exec(select(Genre).where(Genre.genre_name == genre_name)).first()
        existing_decade = db.exec(select(Decade).where(Decade.decade_name == decade_name)).first()



        if existing_genre and existing_decade:
            existing_decade_genre = db.exec(
                select(DecadeGenre).where(
                    (DecadeGenre.decade_id == existing_decade.id) &
                    (DecadeGenre.genre_id == existing_genre.id)
                )
            ).first()

            if existing_decade_genre:
                if not force:
                    logger.warning(f"🚨 ABORT: Decade-Genre combination already exists: {decade_name} / {genre_name}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Decade-Genre '{decade_name}/{genre_name}' already exists. Use force=true to overwrite and reset intro MP3s."
                    )
                else:
                    logger.warning(
                        f"⚠️ Force mode enabled — deleting existing intro MP3s for {decade_name}/{genre_name}")
                    await delete_intro_mp3_files_for_combo(decade_name, genre_name)
                    logger.info(f"✅ Deleted leftover intro MP3s for {decade_name}/{genre_name} before reinserting.")

        genre = db.exec(select(Genre).where(Genre.genre_name == genre_name)).first()
        if not genre:
            genre = Genre(genre_name=genre_name)
            db.add(genre)
            db.commit()
            db.refresh(genre)

        decade = db.exec(select(Decade).where(Decade.decade_name == decade_name)).first()
        if not decade:
            decade = Decade(decade_name=decade_name)
            db.add(decade)
            db.commit()
            db.refresh(decade)

        decade_genre = db.exec(
            select(DecadeGenre).where(
                and_(
                    DecadeGenre.decade_id == decade.id,
                    DecadeGenre.genre_id == genre.id
                )
            )
        ).first()
        if not decade_genre:
            decade_genre = DecadeGenre(decade_id=decade.id, genre_id=genre.id)
            db.add(decade_genre)
            db.commit()
            db.refresh(decade_genre)

        artist_map = {}
        for a in data["artist"]:
            sid = a.get("spotify_artist_id")
            name = a["artist_name"].strip()

            if sid:
                stmt = select(Artist).where(Artist.spotify_artist_id == sid)
            else:
                stmt = select(Artist).where(Artist.artist_name == name)

            existing_artist = db.exec(stmt).first()

            if existing_artist:
                artist_id = existing_artist.id

                desc = a.get("artist_description")
                if not preserve_artist_description or not existing_artist.artist_description or not existing_artist.artist_description.strip():
                    existing_artist.artist_description = desc
                    logger.info(f"📝 Updated artist_description for: {name}")
            else:
                artist = Artist(
                    artist_name=name,
                    spotify_artist_id=sid,
                    artist_artwork=a.get("artist_artwork"),
                    artist_description=a.get("artist_description"),
                    not_on_spotify=a.get("not_on_spotify", False)
                )
                db.add(artist)
                db.commit()
                db.refresh(artist)
                artist_id = artist.id
                logger.info(f"➕ Added artist: {name}")

            artist_map[sid or name] = artist_id

            if not db.exec(select(ArtistGenre).where(
                ArtistGenre.artist_id == artist_id,
                ArtistGenre.genre_id == genre.id
            )).first():
                db.add(ArtistGenre(artist_id=artist_id, genre_id=genre.id))

        db.commit()

        track_map = {}
        for t in data["track"]:
            sid = t.get("spotify_track_id")
            artist_sid = t.get("spotify_artist_id")
            artist_id = artist_map.get(artist_sid or t["artist_name"].strip())

            raw_flag = t.get("mode_flag")
            parsed_flag = parse_mode_flag(raw_flag)

            with db.no_autoflush:
                track = db.exec(
                    select(Track).where(Track.spotify_track_id == sid)
                ).first() if sid else db.exec(
                    select(Track).where(
                        (Track.track_name == t["track_name"]) &
                        (Track.artist_id == artist_id)
                    )
                ).first()

            featured_artist_id = None
            if parsed_flag in (ModeFlag.DUET, ModeFlag.FEATURED):
                feat_sid = t.get("featured_artist_sid")
                feat_name = t.get("featured_artist_name", "").strip()
                featured_artist_id = artist_map.get(feat_sid or feat_name)

            if track:
                logger.info(f"🔁 Updating track: {t['track_name']}")
                track.track_name = t["track_name"]
                track.artist_display_name = t.get("artist_display_name")
                track.artist_id = artist_id
                track.featured_artist_id = featured_artist_id
                track.duration_ms = t["duration_ms"]
                track.popularity = t["popularity"]
                track.album_artwork = t["album_artwork"]
                track.year_released = t["year_released"]
                track.is_explicit = t["is_explicit"]
                track.created_at = t["created_at"]
                track.album_name = t.get("album_name")
                track.mode_flag = parsed_flag.value

                detail = t.get("detail")
                if not preserve_detail or not track.detail or not track.detail.strip():
                    track.detail = detail
                    logger.info(f"📝 Updated detail for: {t['track_name']}")
            else:
                logger.info(f"➕ Creating new track: {t['track_name']}")
                track = Track(
                    track_name=t["track_name"],
                    artist_display_name=t.get("artist_display_name"),
                    artist_id=artist_id,
                    featured_artist_id=featured_artist_id,
                    spotify_track_id=sid,
                    duration_ms=t["duration_ms"],
                    popularity=t["popularity"],
                    album_artwork=t["album_artwork"],
                    year_released=t["year_released"],
                    is_explicit=t["is_explicit"],
                    created_at=t["created_at"],
                    detail=t.get("detail"),
                    album_name=t.get("album_name"),
                    mode_flag=parsed_flag.value
                )
                db.add(track)
                db.commit()
                db.refresh(track)

            track_map[(track.track_name, artist_id)] = track.id

        db.commit()

        for r in data.get("track_ranking", []):
            spotify_tid = r.get("track_id")
            if not spotify_tid:
                logger.warning("🚫 Skipping ranking entry — no track_id")
                continue

            stmt_track = select(Track).where(Track.spotify_track_id == spotify_tid)
            track_obj = db.exec(stmt_track).first()
            if not track_obj:
                logger.warning(f"🚫 Track not found in DB with Spotify ID: {spotify_tid}")
                continue

            tid = track_obj.id

            stmt_ranking = select(TrackRanking).where(
                (TrackRanking.track_id == tid) &
                (TrackRanking.decade_genre_id == decade_genre.id) &
                (TrackRanking.tracklist_id == 1)
            )
            ranking = db.exec(stmt_ranking).first()

            if ranking:
                ranking.ranking = r["rank"]
                ranking.created_at = r["created_at"]

                intro = r.get("intro")
                if not preserve_intro or not ranking.intro or not ranking.intro.strip():
                    ranking.intro = intro
                    logger.info(f"📝 Updated intro for: {track_obj.track_name}")
            else:
                db.add(TrackRanking(
                    track_id=tid,
                    decade_genre_id=decade_genre.id,
                    tracklist_id=1,
                    ranking=r["rank"],
                    intro=r.get("intro"),
                    created_at=r["created_at"]
                ))
                logger.info(f"✅ Added ranking for: {track_obj.track_name}")

        db.commit()

        logger.info("✅ JSON import complete.")
        return {"status": "success", "message": f"Inserted {filename}"}

    except Exception as e:
        db.rollback()
        logger.error(f"🔥 DB error: {e}")
        raise HTTPException(500, f"DB error: {e}")
