import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Path, Depends
from pydantic import BaseModel, Field
from typing import Literal
from sqlmodel import Session, select

from backend.services.spotify_service import get_spotify_data
from backend.services.xai_service import (
    get_top_tracks_from_xai,
    get_track_descriptions_from_xai,
    get_artist_description  # ⬅️ Add this
)

from backend.database import get_db
from models.dbmodels import Genre, Decade, Artist, Track, TrackRanking, DecadeGenre, Tracklist
from shared.filepaths import get_json_path

router = APIRouter()

# === /generate-json ===

class TrackRequest(BaseModel):
    category: str = Field(..., description="Decade/category, e.g. '1960s'")
    genre: str = Field(..., description="Genre, e.g. 'rock'")
    language: Literal["English", "Spanish"] = Field(..., description="Language used for TTS and descriptions")
    num_tracks: int = Field(..., ge=1, le=50, description="Number of tracks to generate (1–50)")

@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
def generate_track_json(request: TrackRequest):
    wrapped = get_top_tracks_from_xai(
        category=request.category,
        genre=request.genre,
        num_tracks=request.num_tracks,
        language=request.language
    )

    if not wrapped or "tracks" not in wrapped:
        raise HTTPException(status_code=500, detail="Failed to retrieve track list from XAI")

    track_list = wrapped["tracks"]

    enriched = get_track_descriptions_from_xai(
        track_data=wrapped,
        language=request.language,
        category=request.category,
        genre=request.genre
    )

    logging.info(f"🔍 Enriched keys: {list(enriched.keys())}")
    logging.info(f"🔢 Track count in enriched['tracks']: {len(enriched.get('tracks', []))}")

    if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
        raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

    now = datetime.now().isoformat()
    artists = []
    tracks = []
    rankings = []

    description_cache = {}

    for base in enriched["tracks"]:
        spotify_data = get_spotify_data(base['trackName'], base['artistName'])
        artist_name = base["artistName"]

        # Cache description
        if artist_name not in description_cache:
            logging.info(f"🔍 Fetching description for: {artist_name}")
            desc = get_artist_description(artist_name, language=request.language)
            logging.info(f"✅ Got description: {desc}")
            if not desc:
                desc = "No biography available at this time."
            description_cache[artist_name] = desc

        artist_entry = {
            "name": artist_name,
            "spotify_artist_id": spotify_data.get("artistId") if spotify_data else None,
            "artist_artwork": None,
            "artist_description": description_cache[artist_name]
        }

        if not any(a["name"] == artist_name for a in artists):
            artists.append(artist_entry)

        track_entry = {
            "track_name": base["trackName"],
            "artist_name": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "spotify_track_id": spotify_data.get("id") if spotify_data else None,
            "duration_ms": spotify_data.get("durationMs") if spotify_data else None,
            "popularity": spotify_data.get("popularity") if spotify_data else None,
            "album_artwork": spotify_data.get("trackImage") if spotify_data else None,
            "year_released": int(base["yearReleased"]),
            "is_explicit": False,
            "created_at": now,
            "detail": base.get("detail")
        }

        tracks.append(track_entry)

        rankings.append({
            "track_name": base["trackName"],
            "artist_name": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "tracklist": "TopSpot Autogen",
            "rank": base["rank"],
            "intro": base.get("intro"),
            "intro_mp3_url": base.get("intro_mp3_url"),
            "ranking_date": now[:10]
        })

    print("👀 Artists list before writing JSON:")
    print(json.dumps(artists, indent=2))

    final_json = {
        "core_tables": {
            "genre": [{"name": request.genre}],
            "decade": [{"name": request.category}],
            "artist": artists
        },
        "track_tables": {
            "track": tracks,
            "tracklist": [
                {
                    "name": "TopSpot Autogen",
                    "curator": "Mr. Ed",
                    "is_official": True,
                    "language": request.language[:2].lower(),
                    "notes": f"Generated for {request.category} - {request.genre}",
                    "created_at": now
                }
            ]
        },
        "ranking_tables": {
            "trackranking": rankings
        }
    }

    filepath = get_json_path(request.category, request.genre, request.language[:2])
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write JSON: {e}")

    return {"message": "🎉 JSON created successfully", "file": str(filepath)}

# === /validate-json ===

REQUIRED_FIELDS = [
    "rank", "track_name", "artist_name", "intro", "intro_mp3_url", "ranking_date"
]

@router.get("/validate-json/{decade}/{filename}")
def validate_json_file(
    decade: str = Path(..., description="Decade folder name, e.g. '1960s'"),
    filename: str = Path(..., description="Filename like '1960s_rock_en.json'")
):
    filepath = os.path.join("data/json_files/genredecade", decade, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        rankings = data.get("ranking_tables", {}).get("trackranking", [])
        errors = []

        for idx, track in enumerate(rankings, start=1):
            missing = [field for field in REQUIRED_FIELDS if field not in track]
            if missing:
                errors.append({
                    "rank": track.get("rank", idx),
                    "track_name": track.get("track_name", "Unknown"),
                    "missing_fields": missing
                })

        if errors:
            return {
                "status": "error",
                "message": f"{len(errors)} tracks have missing fields",
                "errors": errors
            }
        else:
            return {
                "status": "success",
                "message": "All tracks are valid ✅",
                "totalTracks": len(rankings)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating JSON file: {e}")

# === /insert-json-to-db ===

@router.post("/insert-json-to-db/{decade}/{filename:path}", summary="Load a JSON file from disk and insert it into the DB")
def insert_json_to_db(
    decade: str = Path(..., description="Decade folder name"),
    filename: str = Path(..., description="JSON file name"),
    db: Session = Depends(get_db)
):
    filepath = os.path.join("data/json_files/genredecade", decade, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="JSON file not found")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

    try:
        genre_name = data["core_tables"]["genre"][0]["name"]
        decade_name = data["core_tables"]["decade"][0]["name"]

        genre = db.exec(select(Genre).where(Genre.name == genre_name)).first()
        if not genre:
            genre = Genre(name=genre_name)
            db.add(genre)
            db.commit()
            db.refresh(genre)

        decade = db.exec(select(Decade).where(Decade.name == decade_name)).first()
        if not decade:
            decade = Decade(name=decade_name)
            db.add(decade)
            db.commit()
            db.refresh(decade)

        for artist_data in data["core_tables"]["artist"]:
            existing = db.exec(select(Artist).where(Artist.name == artist_data["name"])).first()
            if not existing:
                artist = Artist(
                    name=artist_data["name"],
                    spotify_artist_id=artist_data["spotify_artist_id"],
                    artist_artwork=artist_data.get("artist_artwork")
                )
                db.add(artist)
        db.commit()

        for track_data in data["track_tables"]["track"]:
            artist = db.exec(select(Artist).where(Artist.name == track_data["artist_name"])).first()
            existing = db.exec(select(Track).where(
                Track.name == track_data["track_name"], Track.artistid == artist.id)).first()
            if not existing:
                track = Track(
                    name=track_data["track_name"],
                    artistid=artist.id,
                    genre_id=genre.id,
                    decade_id=decade.id,
                    spotify_track_id=track_data["spotify_track_id"],
                    duration_ms=track_data["duration_ms"],
                    popularity=track_data["popularity"],
                    album_artwork=track_data["album_artwork"],
                    year_released=track_data["year_released"],
                    is_explicit=track_data["is_explicit"],
                    created_at=track_data["created_at"],
                    detail=track_data.get("detail")
                )
                db.add(track)
        db.commit()

        for rank_data in data["ranking_tables"]["trackranking"]:
            artist = db.exec(select(Artist).where(Artist.name == rank_data["artist_name"])).first()
            track = db.exec(select(Track).where(Track.name == rank_data["track_name"], Track.artistid == artist.id)).first()

            decade_genre = db.exec(
                select(DecadeGenre).where(
                    DecadeGenre.decade_id == decade.id,
                    DecadeGenre.genre_id == genre.id
                )
            ).first()

            tracklist = db.exec(select(Tracklist).where(Tracklist.name == rank_data["tracklist"])).first()
            tracklist_id = tracklist.id if tracklist else 1

            existing = db.exec(select(TrackRanking).where(
                TrackRanking.track_id == track.id,
                TrackRanking.decade_genre_id == decade_genre.id,
                TrackRanking.tracklist_id == tracklist_id
            )).first()

            if not existing:
                ranking = TrackRanking(
                    track_id=track.id,
                    decade_genre_id=decade_genre.id,
                    tracklist_id=tracklist_id,
                    ranking=rank_data["rank"],
                    intro=rank_data.get("intro"),
                    intro_mp3_url=rank_data.get("intro_mp3_url"),
                    ranking_date=rank_data["ranking_date"]
                )
                db.add(ranking)

        db.commit()
        return {"status": "success", "message": f"Inserted data from {filename} into database"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
