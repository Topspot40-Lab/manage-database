# backend/routers/supabase_loader.py

from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from backend.database import get_db
from backend.models import TrackRanking, Track, Artist, Decade, Genre, DecadeGenre
from backend.utils.tts_diagnostics import normalize_for_filename

import logging

router = APIRouter(prefix="/supabase", tags=["Supabase"])
logger = logging.getLogger("supabase_loader")

@router.get("/play-track-by-rank")
async def play_track_by_rank(
    decade: str = Query(..., description="Decade name, e.g., '1980s'"),
    genre: str = Query(..., description="Genre name, e.g., 'country'"),
    rank: int = Query(..., description="Rank of the track"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_mp3: bool = Query(True),
    db: Session = Depends(get_db)
):
    logger.info(f"🎯 Playing track by rank: {decade} / {genre} / #{rank}")

    # Step 1: Lookup DecadeGenre
    stmt = (
        select(DecadeGenre)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .where(Decade.decade_name == decade)
        .where(Genre.genre_name == genre)
    )
    decade_genre = db.exec(stmt).first()
    if not decade_genre:
        return {"error": f"No DecadeGenre found for {decade} / {genre}"}

    # Step 2: Lookup TrackRanking
    tr_stmt = select(TrackRanking).where(
        TrackRanking.decade_genre_id == decade_genre.id,
        TrackRanking.ranking == rank
    )
    ranking = db.exec(tr_stmt).first()
    if not ranking:
        return {"error": f"No ranking #{rank} found in {decade} / {genre}"}

    # Step 3: Load Track
    track = db.get(Track, ranking.track_id)
    if not track:
        return {"error": f"Track ID {ranking.track_id} not found"}

    # Step 4: Load Artist
    artist = db.get(Artist, track.artist_id)
    if not artist:
        return {"error": f"Artist ID {track.artist_id} not found"}

    # === File keys ===
    intro_mp3 = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02}.mp3"
    detail_mp3 = f"{track.spotify_track_id}.mp3"
    track_mp3 = f"{track.spotify_track_id}.mp3"
    artist_mp3 = f"{artist.spotify_artist_id}.mp3"

    # === Playback (stubbed in this example — plug in your actual player) ===
    from backend.services.supabase_playback import play_mp3  # adjust import as needed

    if play_intro:
        logger.info(f"🎙️ Playing intro MP3: {intro_mp3}")
        await play_mp3("track_intro_mp3_files", intro_mp3)

    if play_detail:
        logger.info(f"📖 Playing detail MP3: {detail_mp3}")
        await play_mp3("track_detail_mp3_files", detail_mp3)

    if play_track:
        logger.info(f"🎵 Playing track MP3: {track_mp3}")
        await play_mp3("spotify_track_mp3_files", track_mp3)

    if play_artist_mp3:
        logger.info(f"🎤 Playing artist MP3: {artist_mp3}")
        await play_mp3("artist_mp3_files", artist_mp3)

    return {
        "status": "success",
        "track": track.track_name,
        "artist": artist.artist_name,
        "played": {
            "intro": play_intro,
            "detail": play_detail,
            "track": play_track,
            "artist": play_artist_mp3
        }
    }



@router.get("/load-decade-genre-data")
def load_decade_genre_data(
    decade: str = Query(..., description="Decade name, e.g., '1980s'"),
    genre: str = Query(..., description="Genre name, e.g., 'country'"),
    db: Session = Depends(get_db)
):
    logger.info(f"📥 Loading track data for {decade} / {genre}")

    # Step 1: Lookup DecadeGenre
    stmt = (
        select(DecadeGenre)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .where(Decade.decade_name == decade)
        .where(Genre.genre_name == genre)
    )
    decade_genre = db.exec(stmt).first()
    if not decade_genre:
        return {"error": f"No DecadeGenre found for {decade} / {genre}"}

    # Step 2: Get all TrackRanking entries for this combo
    rankings = db.exec(
        select(TrackRanking).where(TrackRanking.decade_genre_id == decade_genre.id)
    ).all()

    response = []
    for rank_entry in rankings:
        track = db.get(Track, rank_entry.track_id)
        if not track:
            logger.warning(f"⚠️ Track ID {rank_entry.track_id} not found")
            continue

        artist = db.get(Artist, track.artist_id)
        if not artist:
            logger.warning(f"⚠️ Artist ID {track.artist_id} not found")
            continue

        # Build file keys
        intro_mp3 = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank_entry.ranking:02}.mp3"
        detail_mp3 = f"{track.spotify_track_id}.mp3"
        track_mp3 = f"{track.spotify_track_id}.mp3"
        artist_mp3 = f"{artist.spotify_artist_id}.mp3"

        response.append({
            "rank": rank_entry.ranking,
            "trackName": track.track_name,
            "artistName": artist.artist_name,
            "intro": rank_entry.intro,
            "detail": track.detail,
            "artistDescription": artist.artist_description,
            "introMp3": intro_mp3,
            "detailMp3": detail_mp3,
            "trackMp3": track_mp3,
            "artistMp3": artist_mp3,
            "artistArtwork": artist.artist_artwork,
            "albumArtwork": track.album_artwork
        })

    logger.info(f"✅ Loaded {len(response)} ranked tracks for {decade} / {genre}")
    return {
        "decade": decade,
        "genre": genre,
        "track_count": len(response),
        "rankings": sorted(response, key=lambda x: x["rank"])
    }
