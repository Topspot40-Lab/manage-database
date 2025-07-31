from fastapi import APIRouter, HTTPException, Path, Depends
from sqlmodel import Session, select
import logging
import sqlalchemy
from backend.utils.mode_utils import ModeFlag
from sqlalchemy import and_

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

        # 🔍 Log the raw structure of the JSON
        logger.debug(f"🧩 Raw JSON keys: {list(data.keys())}")
        logger.debug(f"🧩 type(data['artist']) = {type(data.get('artist'))}")
        logger.debug(f"🧩 data['artist'] (first 100 chars): {str(data.get('artist'))[:100]}")

        # 🛠️ PATCH: Ensure artist block is always a list
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
        # genre_name = data["genre"][0]["genre_name"]
        # decade_name = data["decade"][0]["decade_name"]

        genre_name = data["genre"]
        decade_name = data["category"]

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
            logger.info("Linked DecadeGenre")

        logger.debug(f"type(data['artist']) = {type(data['artist'])}")
        logger.debug(f"data['artist'][:1] = {data['artist'][:1]}")

        # Deduplicate artists
        artist_map = {}
        for a in data["artist"]:
            sid = a.get("spotify_artist_id")
            name = a["artist_name"].strip()

            # Safer and clearer artist lookup logic
            if sid:
                stmt = select(Artist).where(Artist.spotify_artist_id == sid)
            else:
                stmt = select(Artist).where(Artist.artist_name == name)

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

        logger.debug(f"🔍 type(data['track']) = {type(data.get('track'))}")
        logger.debug(
            f"🔍 data['track'] (first item) = {data['track'][0] if isinstance(data['track'], list) and data['track'] else 'EMPTY'}")

        # Insert tracks
        track_map = {}
        for t in data["track"]:
            sid = t.get("spotify_track_id")
            artist_sid = t.get("spotify_artist_id")
            artist_id = artist_map.get(artist_sid or t["artist_name"].strip())

            logger.debug(f"🧪 Inserting track: {t.get('track_name')} | raw_flag: {t.get('mode_flag')}")

            # ───── Step 1: Parse the mode flag ─────
            raw_flag = t.get("mode_flag")
            parsed_flag = parse_mode_flag(raw_flag)

            # ───── Step 2: Lookup existing track ─────
            try:
                with db.no_autoflush:
                    track = db.exec(
                        select(Track).where(Track.spotify_track_id == sid)
                    ).first() if sid else db.exec(
                        select(Track).where(
                            (Track.track_name == t["track_name"]) &
                            (Track.artist_id == artist_id)
                        )
                    ).first()
            except Exception as e:
                logger.error(f"🔥 Exception during db.exec: {e}")
                logger.error(f"❗ t['track_name'] = {t.get('track_name')}, artist_id = {artist_id}, sid = {sid}")
                raise

            # ───── Step 3: Determine featured_artist_id if needed ─────
            featured_artist_id = None
            if parsed_flag in (ModeFlag.DUET, ModeFlag.FEATURED):
                feat_sid = t.get("featured_artist_sid")
                feat_name = t.get("featured_artist_name", "").strip()
                featured_artist_id = artist_map.get(feat_sid or feat_name)
                if not featured_artist_id:
                    logger.warning(
                        f"⚠️ Could not resolve featured artist for track: {t['track_name']} | SID: {feat_sid} | Name: {feat_name}")

            logger.debug(f"🎤 Mode: {parsed_flag} | Featured ID: {featured_artist_id}")

            # ───── Step 4: Create or update the track ─────
            if track:
                logger.info(f"🔁 Updating track: {t['track_name']}")
                track.track_name = t["track_name"]
                track.artist_display_name = t.get("artist_display_name")
                track.artist_id = artist_id
                track.featured_artist_id = featured_artist_id  # ✅ NEW
                track.duration_ms = t["duration_ms"]
                track.popularity = t["popularity"]
                track.album_artwork = t["album_artwork"]
                track.year_released = t["year_released"]
                track.is_explicit = t["is_explicit"]
                track.created_at = t["created_at"]
                track.detail = t.get("detail")
                track.album_name = t.get("album_name")
                track.mode_flag = parsed_flag.value
            else:
                logger.info(f"➕ Creating new track: {t['track_name']}")
                track = Track(
                    track_name=t["track_name"],
                    artist_display_name=t.get("artist_display_name"),
                    artist_id=artist_id,
                    featured_artist_id=featured_artist_id,  # ✅ NEW
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

        logger.debug(f"✅ type(data['track_ranking']): {type(data['track_ranking'])}")
        logger.debug(f"✅ data['track_ranking']: {data['track_ranking']}")
        # Insert rankings
        for i, r in enumerate(data.get("track_ranking", [])):
            logger.debug(f"🧪 Ranking #{i}: {r} (type: {type(r)})")

            if not isinstance(r, dict):
                logger.error(f"🚫 Malformed ranking entry (not a dict): {r}")
                continue  # Skip this one

            spotify_tid = r.get("track_id")
            if not spotify_tid:
                logger.error(f"🚫 No spotify_track_id in ranking entry: {r}")
                continue

            stmt_track = select(Track).where(Track.spotify_track_id == spotify_tid)
            track_obj = db.exec(stmt_track).first()

            if not track_obj:
                logger.error(f"🚫 Track not found in DB with Spotify ID: {spotify_tid}")
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
                ranking.intro = r.get("intro")
                ranking.created_at = r["created_at"]
                logger.info(f"📝 Updated ranking for: {track_obj.track_name}")
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


        logger.info("JSON import complete.")
        return {"status": "success", "message": f"Inserted {filename}"}

    except Exception as e:
        db.rollback()
        logger.error(f"DB error: {e}")
        raise HTTPException(500, f"DB error: {e}")
