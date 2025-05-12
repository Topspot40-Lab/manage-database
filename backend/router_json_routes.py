import os
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Path, Depends
from pydantic import BaseModel, Field
from typing import Literal
from sqlmodel import Session, select

from backend.services.spotify_service import get_spotify_data
from backend.services.xai_service import get_top_tracks_from_xai, get_track_descriptions_from_xai
from backend.database import get_db
from backend.dbmodels import Genre, Decade, Artist, Track, TrackRanking
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

    if not enriched or "tracks" not in enriched or len(enriched["tracks"]) != len(track_list):
        raise HTTPException(status_code=500, detail="Mismatch or failure in track descriptions")

    now = datetime.now().isoformat()
    artists = []
    tracks = []
    rankings = []

    for base in enriched["tracks"]:
        spotify_data = get_spotify_data(base['trackName'], base['artistName'])

        artist_entry = {
            "name": base["artistName"],
            "spotify_artist_id": spotify_data.get("artistId") if spotify_data else None,
            "artist_artwork": None,
            "artist_description": ""
        }
        if artist_entry not in artists:
            artists.append(artist_entry)

        track_entry = {
            "name": base["trackName"],
            "artistName": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "spotify_track_id": spotify_data.get("id") if spotify_data else None,
            "duration_ms": spotify_data.get("durationMs") if spotify_data else None,
            "popularity": spotify_data.get("popularity") if spotify_data else None,
            "album_artwork": spotify_data.get("trackImage") if spotify_data else None,
            "year_released": int(base["yearReleased"]),
            "is_explicit": False,
            "created_at": now
        }
        tracks.append(track_entry)

        rankings.append({
            "trackName": base["trackName"],
            "artistName": base["artistName"],
            "genre": request.genre,
            "decade": request.category,
            "tracklist": "TopSpot Autogen",
            "rank": base["rank"],
            "intro": base.get("intro"),
            "detail": base.get("detail"),
            "description_language": request.language,
            "ranking_date": now[:10]
        })

    final_json = {
        "core_tables": {
            "genre": [{"name": request.genre}],
            "decade": [{"name": request.category}],
            "artist": artists,
            "language": [{"code": request.language[:2].lower(), "name": request.language}],
            "specialty": []
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
    "rank", "trackName", "artistName", "durationMs", "trackId", "artistId",
    "albumArtwork", "intro", "detail", "yearReleased"
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

        tracks = data.get("ranking_tables", {}).get("trackranking", [])
        errors = []

        for idx, track in enumerate(tracks, start=1):
            missing = [field for field in REQUIRED_FIELDS if field not in track]
            if missing:
                errors.append({
                    "rank": track.get("rank", idx),
                    "trackName": track.get("trackName", "Unknown"),
                    "missingFields": missing
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
                "totalTracks": len(tracks)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating JSON file: {e}")


# === /insert-json-to-db ===

@router.post("/insert-json-to-db")
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
            artist = db.exec(select(Artist).where(Artist.name == track_data["artistName"])).first()
            existing = db.exec(select(Track).where(
                Track.name == track_data["name"], Track.artist_id == artist.id)).first()
            if not existing:
                track = Track(
                    name=track_data["name"],
                    artist_id=artist.id,
                    genre_id=genre.id,
                    decade_id=decade.id,
                    spotify_track_id=track_data["spotify_track_id"],
                    duration_ms=track_data["duration_ms"],
                    popularity=track_data["popularity"],
                    album_artwork=track_data["album_artwork"],
                    year_released=track_data["year_released"],
                    is_explicit=track_data["is_explicit"],
                    created_at=track_data["created_at"]
                )
                db.add(track)
        db.commit()

        for rank_data in data["ranking_tables"]["trackranking"]:
            artist = db.exec(select(Artist).where(Artist.name == rank_data["artistName"])).first()
            track = db.exec(select(Track).where(Track.name == rank_data["trackName"], Track.artist_id == artist.id)).first()
            existing = db.exec(select(TrackRanking).where(TrackRanking.track_id == track.id)).first()
            if not existing:
                ranking = TrackRanking(
                    track_id=track.id,
                    genre_id=genre.id,
                    decade_id=decade.id,
                    rank=rank_data["rank"],
                    tracklist=rank_data["tracklist"],
                    intro=rank_data["intro"],
                    detail=rank_data["detail"],
                    description_language=rank_data["description_language"],
                    ranking_date=rank_data["ranking_date"]
                )
                db.add(ranking)
        db.commit()

        return {"status": "success", "message": f"Inserted data from {filename} into database"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
