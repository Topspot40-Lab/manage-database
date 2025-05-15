# import os
from fastapi import APIRouter, HTTPException, Path, Depends
from sqlmodel import Session, select

from backend.database import get_db
from backend.models import Genre, Decade, Artist, Track, TrackRanking
from utils.json_helpers import load_json

router = APIRouter(prefix="", tags=["json-insert"])

@router.post("/insert-json-to-db/{decade}/{filename:path}")
def insert_json_to_db(
    decade: str = Path(...), filename: str = Path(...), db: Session = Depends(get_db)
):
    try:
        data = load_json(decade, filename)
    except FileNotFoundError:
        raise HTTPException(404, "JSON file not found")
    except Exception as e:
        raise HTTPException(500, f"Read error: {e}")

    try:
        # === 1. genre / decade ===
        genre_name   = data["core_tables"]["genre"][0]["name"]
        decade_name  = data["core_tables"]["decade"][0]["name"]

        # noinspection PyTypeChecker
        genre  = db.exec(select(Genre).where(Genre.name == genre_name)).first() \
                 or Genre(name=genre_name)
        # noinspection PyTypeChecker
        decade = db.exec(select(Decade).where(Decade.name == decade_name)).first() \
                 or Decade(name=decade_name)
        db.add_all([genre, decade]); db.commit()
        db.refresh(genre); db.refresh(decade)

        # === 2. artists ===
        for a in data["core_tables"]["artist"]:
            db.merge(Artist(
                name=a["name"],
                spotify_artist_id=a["spotify_artist_id"],
                artist_artwork=a.get("artist_artwork"),
            ))
        db.commit()

        # === 3. tracks ===
        for t in data["track_tables"]["track"]:
            # noinspection PyTypeChecker
            artist = db.exec(select(Artist).where(Artist.name == t["artistName"])).first()
            db.merge(Track(
                name=t["name"], artistid=artist.id, genre_id=genre.id,
                decade_id=decade.id, spotify_track_id=t["spotify_track_id"],
                duration_ms=t["duration_ms"], popularity=t["popularity"],
                album_artwork=t["album_artwork"], year_released=t["year_released"],
                is_explicit=t["is_explicit"], created_at=t["created_at"],
            ))
        db.commit()

        # === 4. rankings ===
        for r in data["ranking_tables"]["trackranking"]:
            # noinspection PyTypeChecker
            artist = db.exec(select(Artist).where(Artist.name == r["artistName"])).first()
            # noinspection PyTypeChecker
            track  = db.exec(select(Track).where(
                        Track.name == r["trackName"], Track.artistid == artist.id)).first()
            db.merge(TrackRanking(
                trackid=track.id, genre_id=genre.id, decade_id=decade.id,
                rank=r["rank"], tracklist=r["tracklist"],
                intro=r["intro"], detail=r["detail"],
                description_language=r["description_language"],
                ranking_date=r["ranking_date"],
            ))
        db.commit()

        return {"status": "success", "message": f"Inserted {filename}"}

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"DB error: {e}")
