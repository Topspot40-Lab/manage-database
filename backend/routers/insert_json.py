from fastapi import APIRouter, HTTPException, Path, Depends
from sqlmodel import Session, select
import logging

from backend.database import get_db
from backend.models import Genre, Decade, DecadeGenre, Artist, ArtistGenre, Track, TrackRanking
from utils.json_helpers import load_json

router = APIRouter(prefix="", tags=["json-insert"])

@router.post("/insert-json-to-db/{decade}/{genre}")
def insert_json_to_db(
    decade: str = Path(...),
    genre: str = Path(...),
    db: Session = Depends(get_db)
):

    import sqlalchemy
    print(f"✯ Connected to DB and using schema: {sqlalchemy.inspect(db.bind).default_schema_name}")

    # === 1. Load JSON File ===
    try:
        filename = f"{decade}_{genre}_en.json"
        data = load_json(decade, filename)
        logging.info(f"📂 Loaded JSON file: {filename}")
    except FileNotFoundError:
        logging.error("❌ JSON file not found")
        raise HTTPException(404, "JSON file not found")
    except Exception as e:
        logging.error(f"❌ Error reading JSON: {e}")
        raise HTTPException(500, f"Read error: {e}")

    try:
        # === 2. Handle Genre and Decade ===
        genre_name = data["core_tables"]["genre"][0]["genre_name"]
        decade_name = data["core_tables"]["decade"][0]["decade_name"]
        logging.info(f"🎼 Genre: {genre_name}, 📅 Decade: {decade_name}")

        genre = db.exec(select(Genre).where(Genre.genre_name == genre_name)).first()
        if not genre:
            genre = Genre(genre_name=genre_name)
            db.add(genre)
            db.commit()
            db.refresh(genre)
            logging.info(f"✅ Added new genre: {genre_name}")

        decade = db.exec(select(Decade).where(Decade.decade_name == decade_name)).first()
        if not decade:
            decade = Decade(decade_name=decade_name)
            db.add(decade)
            db.commit()
            db.refresh(decade)
            logging.info(f"✅ Added new decade: {decade_name}")

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
            logging.info("🔗 Linked DecadeGenre")

        # === 3. Deduplicate Artists in Memory ===
        unique_artists = []
        seen_keys = set()
        for a in data["core_tables"]["artist"]:
            sid = a.get("spotify_artist_id")
            name = a["artist_name"]
            key = sid if sid else name
            if key not in seen_keys:
                unique_artists.append(a)
                seen_keys.add(key)
        data["core_tables"]["artist"] = unique_artists

        # === 4. Insert Artists and ArtistGenre ===
        artist_names_in_json = [a["artist_name"] for a in data["core_tables"]["artist"]]
        spotify_ids_in_json = [a["spotify_artist_id"] for a in data["core_tables"]["artist"] if a.get("spotify_artist_id")]

        existing_artists = db.exec(
            select(Artist).where(
                (Artist.artist_name.in_(artist_names_in_json)) |
                (Artist.spotify_artist_id.in_(spotify_ids_in_json))
            )
        ).all()

        artist_map = {}
        for artist in existing_artists:
            key = artist.spotify_artist_id if artist.spotify_artist_id else artist.artist_name
            artist_map[key] = artist.id

        for a in data["core_tables"]["artist"]:
            artist_name = a["artist_name"].strip()
            sid = a.get("spotify_artist_id")
            key_id = sid if sid else None
            key_name = artist_name

            # Check if this artist already exists by ID or name
            if (key_id and key_id in artist_map) or (key_name in artist_map):
                continue

            if not sid and not a.get("not_on_spotify", False):
                logging.warning(f"⚠️ Missing spotify_artist_id for artist: {artist_name}")
                raise HTTPException(400, f"Missing spotify_artist_id for artist: {artist_name}")

            artist = Artist(
                artist_name=artist_name,
                spotify_artist_id=sid,
                artist_artwork=a.get("artist_artwork"),
                artist_description=a.get("artist_description"),
                not_on_spotify=a.get("not_on_spotify", False)
            )
            db.add(artist)
            db.commit()
            db.refresh(artist)
            logging.info(f"🎤 Added artist: {artist_name}")

            # ✅ Insert all relevant keys for lookups
            key = sid if sid else artist_name
            artist_map[artist_name] = artist.id  # always map name
            if sid:
                artist_map[sid] = artist.id  # map ID if available
            artist_map[key] = artist.id  # map whichever key will be used later

            # ✅ Also map whatever key was used to deduplicate
            key = sid if sid else artist_name
            artist_map[key] = artist.id

        for key, artist_id in artist_map.items():
            artist_genre = db.exec(
                select(ArtistGenre).where(
                    ArtistGenre.artist_id == artist_id,
                    ArtistGenre.genre_id == genre.id
                )
            ).first()
            if not artist_genre:
                db.add(ArtistGenre(artist_id=artist_id, genre_id=genre.id))

        db.commit()

        # === 5. Insert Tracks ===
        for t in data["track_tables"]["track"]:
            sid = t.get("spotify_artist_id")
            artist_key = sid or t["artist_name"]
            logging.info(f"🔍 Artist key: {artist_key}")
            logging.info(f"🗜 All artist_map keys: {list(artist_map.keys())}")

            artist_id = artist_map.get(artist_key)
            if not artist_id:
                raise HTTPException(500, f"Artist ID not found for track: {t['track_name']}")

            spotify_tid = t.get("spotify_track_id")
            if not spotify_tid and not t.get("not_on_spotify", False):
                raise HTTPException(400, f"Missing spotify_track_id for track: {t['track_name']}")

            if spotify_tid:
                existing_track = db.exec(
                    select(Track).where(Track.spotify_track_id == spotify_tid)
                ).first()
            else:
                existing_track = db.exec(
                    select(Track).where(
                        Track.track_name == t["track_name"],
                        Track.artist_id == artist_id
                    )
                ).first()

            if existing_track:
                logging.info(f"🔁 Updating track: {t['track_name']}")
                existing_track.track_name = t["track_name"]
                existing_track.track_display_name = t.get("track_display_name")
                existing_track.artist_id = artist_id
                existing_track.duration_ms = t["duration_ms"]
                existing_track.popularity = t["popularity"]
                existing_track.album_artwork = t["album_artwork"]
                existing_track.year_released = t["year_released"]
                existing_track.is_explicit = t["is_explicit"]
                existing_track.created_at = t["created_at"]
                existing_track.not_on_spotify = t.get("not_on_spotify", False)
                existing_track.detail = t.get("detail")
                existing_track.detail_mp3_url = t.get("detail_mp3_url")
            else:
                logging.info(f"➕ Adding track: {t['track_name']}")
                db.add(Track(
                    track_name=t["track_name"],
                    track_display_name=t.get("track_display_name"),
                    artist_id=artist_id,
                    spotify_track_id=spotify_tid,
                    duration_ms=t["duration_ms"],
                    popularity=t["popularity"],
                    album_artwork=t["album_artwork"],
                    year_released=t["year_released"],
                    is_explicit=t["is_explicit"],
                    not_on_spotify=t.get("not_on_spotify", False),
                    created_at=t["created_at"],
                    detail=t.get("detail"),
                    detail_mp3_url=t.get("detail_mp3_url")
                ))

        db.commit()

        # === 6. Insert Track Rankings ===
        for r in data["ranking_tables"]["track_ranking"]:
            track = None
            spotify_tid = r.get("spotify_track_id")
            artist_key = r.get("spotify_artist_id") or r["artist_name"]

            if spotify_tid:
                track = db.exec(
                    select(Track).where(Track.spotify_track_id == spotify_tid)
                ).first()

            if not track:
                track = db.exec(
                    select(Track).where(
                        Track.track_name == r["track_name"],
                        Track.artist_id == artist_map.get(artist_key)
                    )
                ).first()

            if not track:
                logging.error(f"🚫 Track not found for ranking: {r['track_name']}")
                raise HTTPException(500, f"Track not found for ranking: {r['track_name']}")

            existing_ranking = db.exec(
                select(TrackRanking).where(
                    TrackRanking.track_id == track.id,
                    TrackRanking.decade_genre_id == decade_genre.id,
                    TrackRanking.tracklist_id == 1
                )
            ).first()

            logging.info(
                f"🔍 Checking for existing ranking: track_id={track.id}, decade_genre_id={decade_genre.id}, tracklist_id=1")

            if existing_ranking:
                logging.info(f"✅ Found existing ranking: ID={existing_ranking.id}")
                logging.info(f"🔁 Updating ranking for: {r['track_name']}")
                existing_ranking.ranking = r["rank"]
                existing_ranking.intro = r.get("intro")
                existing_ranking.intro_mp3_url = r.get("intro_mp3_url")
                existing_ranking.ranking_date = r["ranking_date"]
            else:
                logging.warning(f"🆕 No existing ranking found — will attempt to insert.")
                db.add(TrackRanking(
                    track_id=track.id,
                    decade_genre_id=decade_genre.id,
                    tracklist_id=1,
                    ranking=r["rank"],
                    intro=r.get("intro"),
                    intro_mp3_url=r.get("intro_mp3_url"),
                    ranking_date=r["ranking_date"]
                ))

            logging.info(f"🏆 Ranked track: {r['track_name']} → #{r['rank']}")

        db.commit()

        logging.info("✅ JSON import complete.")
        return {"status": "success", "message": f"Inserted {filename}"}

    except Exception as e:
        db.rollback()
        logging.error(f"❌ DB error: {e}")
        raise HTTPException(500, f"DB error: {e}")
