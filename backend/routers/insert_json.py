from fastapi import APIRouter, HTTPException, Path, Depends
from sqlmodel import Session, select
import logging
import sqlalchemy
from typing import cast
from sqlmodel.sql.expression import SelectOfScalar
from backend.utils.mode_utils import parse_mode_flag
from backend.database import get_db
from backend.models import Genre, Decade, DecadeGenre, Artist, ArtistGenre, Track, TrackRanking
from backend.utils.json_helpers import load_full_json_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["json-insert"])

@router.post("/insert-json-to-db/{decade}/{genre}")
async def insert_json_to_db(
    decade: str = Path(...),
    genre: str = Path(...),
    db: Session = Depends(get_db)
):
    logger.info(f"Connected to DB and using schema: {sqlalchemy.inspect(db.bind).default_schema_name}")

    try:
        filename = f"{decade}_{genre}_en.json"
        data = load_full_json_file(decade, filename)
        logger.info(f"Loaded JSON file: {filename}")
    except FileNotFoundError:
        logger.error("JSON file not found")
        raise HTTPException(404, "JSON file not found")
    except Exception as e:
        logger.error(f"Error reading JSON: {e}")
        raise HTTPException(500, f"Read error: {e}")

    try:
        genre_name = data["core_tables"]["genre"][0]["genre_name"]
        decade_name = data["core_tables"]["decade"][0]["decade_name"]
        logger.info(f"Genre: {genre_name}, Decade: {decade_name}")

        # noinspection PyTypeChecker
        genre = db.exec(select(Genre).where(Genre.genre_name == genre_name)).first()
        if not genre:
            genre = Genre(genre_name=genre_name)
            db.add(genre)
            db.commit()
            db.refresh(genre)
            logger.info(f"Added new genre: {genre_name}")

        # noinspection PyTypeChecker
        decade = db.exec(select(Decade).where(Decade.decade_name == decade_name)).first()
        if not decade:
            decade = Decade(decade_name=decade_name)
            db.add(decade)
            db.commit()
            db.refresh(decade)
            logger.info(f"Added new decade: {decade_name}")

        # noinspection PyTypeChecker
        decade_genre = db.exec(
            select(DecadeGenre).where(
                DecadeGenre.decade_id == decade.id,
                DecadeGenre.genre_id == genre.id
            )
        ).first()
        if not decade_genre:
            decade_genre = DecadeGenre(decade_id=decade.id, genre_id=genre.id)
            db.add(decade_genre)
            db.commit()
            db.refresh(decade_genre)
            logger.info("Linked DecadeGenre")

        # Deduplicate artists
        artist_map = {}
        for a in data["core_tables"]["artist"]:
            sid = a.get("spotify_artist_id")
            name = a["artist_name"].strip()

            # Safer and clearer artist lookup logic
            if sid:
                stmt = select(Artist).where(Artist.spotify_artist_id == sid)
            else:
                stmt = cast(SelectOfScalar[Artist], select(Artist).where(Artist.spotify_artist_id == sid))

            existing_artist = db.exec(stmt).first()

            if not existing_artist:
                logger.warning(f"🧨 Artist not found: sid='{sid}', name='{name}'")

            if existing_artist:
                artist_id = existing_artist.id
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
                logger.info(f"Added artist: {name}")

            artist_map[sid or name] = artist_id

            # noinspection PyTypeChecker
            if not db.exec(select(ArtistGenre).where(
                ArtistGenre.artist_id == artist_id,
                ArtistGenre.genre_id == genre.id
            )).first():
                db.add(ArtistGenre(artist_id=artist_id, genre_id=genre.id))

        db.commit()

        # Insert tracks
        track_map = {}
        for t in data["track_tables"]["track"]:
            sid = t.get("spotify_track_id")
            artist_sid = t.get("spotify_artist_id")
            artist_id = artist_map.get(artist_sid or t["artist_name"].strip())

            # noinspection PyTypeChecker
            track = db.exec(
                select(Track).where(Track.spotify_track_id == sid)
            ).first() if sid else db.exec(
                select(Track).where(
                    Track.track_name == t["track_name"],
                    Track.artist_id == artist_id
                )
            ).first()

            if track:
                logger.info(f"Updating track: {t['track_name']}")
                track.track_name = t["track_name"]
                track.artist_display_name = t.get("artist_display_name")
                track.artist_id = artist_id
                track.duration_ms = t["duration_ms"]
                track.popularity = t["popularity"]
                track.album_artwork = t["album_artwork"]
                track.year_released = t["year_released"]
                track.is_explicit = t["is_explicit"]
                track.created_at = t["created_at"]
                track.detail = t.get("detail")
                track.album_name = t.get("album_name")  # ✅ Added this field
                raw_flag = t.get("mode_flag")
                parsed_flag = parse_mode_flag(raw_flag)
                logger.info(f"🎛️ Mode flag '{raw_flag}' parsed as → {parsed_flag}")
                track.mode_flag = parsed_flag



            else:
                raw_flag = t.get("mode_flag")
                parsed_flag = parse_mode_flag(raw_flag)
                logger.info(f"🎛️ Mode flag '{raw_flag}' parsed as → {parsed_flag}")

                track = Track(
                    track_name=t["track_name"],
                    artist_display_name=t.get("artist_display_name"),
                    artist_id=artist_id,
                    spotify_track_id=sid,
                    duration_ms=t["duration_ms"],
                    popularity=t["popularity"],
                    album_artwork=t["album_artwork"],
                    year_released=t["year_released"],
                    is_explicit=t["is_explicit"],
                    created_at=t["created_at"],
                    detail=t.get("detail"),
                    album_name=t.get("album_name"),
                    mode_flag=parse_mode_flag(t.get("mode_flag"))  # 👈 THIS is the fix
                )

                db.add(track)
                db.commit()
                db.refresh(track)

            track_map[(track.track_name, artist_id)] = track.id

        db.commit()

        # Insert rankings
        for r in data["ranking_tables"]["track_ranking"]:
            spotify_tid = r.get("track_id")
            if not spotify_tid:
                logger.error(f"🚫 No spotify_track_id in ranking entry: {r}")
                raise HTTPException(500, f"No Spotify track ID for: {r.get('track_name')}")

            # ✅ Fix 1: Use proper Select from SQLAlchemy
            stmt_track = select(Track).where(Track.spotify_track_id == spotify_tid)
            track_obj = db.exec(stmt_track).first()

            if not track_obj:
                logger.error(f"🚫 Track not found in DB with Spotify ID: {spotify_tid}")
                raise HTTPException(500, f"Track not found for Spotify ID: {spotify_tid}")

            tid = track_obj.id
            # ⚠️ artist_id is unused, so it's removed

            # ✅ Fix 2: Use proper Select for ranking
            stmt_ranking = select(TrackRanking).where(
                TrackRanking.track_id == tid,
                TrackRanking.decade_genre_id == decade_genre.id,
                TrackRanking.tracklist_id == 1
            )
            ranking = db.exec(stmt_ranking).first()

            if ranking:
                ranking.ranking = r["rank"]
                ranking.intro = r.get("intro")
                ranking.ranking_date = r["ranking_date"]
                logger.info(f"📝 Updated ranking for: {track_obj.track_name}")
            else:
                db.add(TrackRanking(
                    track_id=tid,
                    decade_genre_id=decade_genre.id,
                    tracklist_id=1,
                    ranking=r["rank"],
                    intro=r.get("intro"),
                    ranking_date=r["ranking_date"]
                ))
                logger.info(f"✅ Added ranking for: {track_obj.track_name}")

        db.commit()


        logger.info("JSON import complete.")
        return {"status": "success", "message": f"Inserted {filename}"}

    except Exception as e:
        db.rollback()
        logger.error(f"DB error: {e}")
        raise HTTPException(500, f"DB error: {e}")
