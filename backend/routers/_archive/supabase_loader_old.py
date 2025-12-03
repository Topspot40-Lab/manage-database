# backend/routers/supabase_loader_legacy.py

from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from backend.database import get_db
from backend.models import TrackRanking, Track, Artist, Decade, Genre, DecadeGenre
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.spotify.playback import play_spotify_track
from backend.state import current_decade_genre, skip_event  # 👈 add skip_event

import logging

router = APIRouter(prefix="/supabase", tags=["Supabase"])
logger = logging.getLogger("supabase_loader")

@router.post("/skip-current-track")
async def skip_current_track():
    """
    Signal the playback loop to skip the current song.
    Your wait helper will see this and return immediately.
    """
    skip_event.set()
    return {"status": "skipping"}

@router.get("/play-track-by-rank-only")
async def play_track_by_rank_only(
    rank: int = Query(..., description="Rank of the track to play"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_mp3: bool = Query(True),
    db: Session = Depends(get_db)
):
    decade = current_decade_genre.get("decade")
    genre = current_decade_genre.get("genre")

    if not decade or not genre:
        return {"error": "No track data loaded. Please load with /load-decade-genre-data first."}

    logger.info(f"🎯 Playing rank #{rank} using cached: {decade} / {genre}")
    return await play_track_by_rank(
        decade=decade,
        genre=genre,
        rank=rank,
        play_intro=play_intro,
        play_detail=play_detail,
        play_track=play_track,
        play_artist_mp3=play_artist_mp3,
        db=db
    )

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
    from backend.config import (
        BUCKET_TRACK_INTRO,
        BUCKET_TRACK_DETAIL,
        BUCKET_ARTIST,
    )
    from backend.services.supabase_playback import play_mp3

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

    logger.info("=" * 90)
    logger.info(
        f"🎯 {decade} / {genre} — Rank #{rank} | 🎵 {track.track_name} by {artist.artist_name} | 🔗 {artist.spotify_artist_id}")

    # === Playback ===
    if play_intro:
        logger.info(f"\n📢 Intro Text (→ {intro_mp3}):\n{ranking.intro.strip()}")
        await play_mp3(BUCKET_TRACK_INTRO, intro_mp3)

    if play_detail:
        logger.info(f"\n📝 Detail Text (→ {detail_mp3}):\n{track.detail.strip()}")
        await play_mp3(BUCKET_TRACK_DETAIL, detail_mp3)

    if play_artist_mp3:
        logger.info(f"\n🎙️ Artist Description:\n{artist.artist_description.strip()}")
        await play_mp3(BUCKET_ARTIST, artist_mp3)

    # === Log Artwork URLs After Playback Starts ===
    if artist.artist_artwork:
        logger.info(f"🖼️ Artist Artwork: {artist.artist_artwork}")
    else:
        logger.info("🖼️ Artist Artwork: [None]")

    if track.album_artwork:
        logger.info(f"💿 Album Artwork: {track.album_artwork}")
    else:
        logger.info("💿 Album Artwork: [None]")

    if play_track:
        logger.debug(f"🎵 Playing track MP3: {track_mp3}")
        play_spotify_track(track.spotify_track_id)




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
    # ✅ Remember the context
    current_decade_genre["decade"] = decade
    current_decade_genre["genre"] = genre
    logger.info(f"📌 Stored context for play-by-rank-only: {decade} / {genre}")

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

@router.get("/play-tracks-with-starting-rank")
async def play_tracks_with_starting_rank(
    starting_rank: int = Query(...),
    mode: str = Query("count_up"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_mp3: bool = Query(True),
    db: Session = Depends(get_db)
):
    import random, asyncio, logging
    from sqlmodel import select
    from backend.config import (
        BUCKET_TRACK_INTRO, BUCKET_TRACK_DETAIL, BUCKET_ARTIST,
        SPOTIFY_BED_TRACK_ID, BED_FACTOR
    )
    from backend.services.supabase_playback import play_mp3
    from backend.services.spotify.spotify_auth_user import get_spotify_user_client
    from backend.utils.tts_diagnostics import normalize_for_filename
    from backend.models import Decade, Genre, DecadeGenre, TrackRanking, Track, Artist
    from backend.state import current_decade_genre

    logger = logging.getLogger("play_tracks_with_starting_rank")

    decade = current_decade_genre.get("decade")
    genre = current_decade_genre.get("genre")
    if not decade or not genre:
        return {"error": "No track data loaded. Please load with /load-decade-genre-data first."}

    # --- Resolve DecadeGenre
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

    rankings = db.exec(
        select(TrackRanking)
        .where(TrackRanking.decade_genre_id == decade_genre.id)
        .order_by(TrackRanking.ranking)
    ).all()
    if not rankings:
        return {"error": "No rankings found."}

    total_tracks = len(rankings)
    available_ranks = list(range(1, total_tracks + 1))

    if mode == "count_up":
        play_order = [r for r in available_ranks if r >= starting_rank]
    elif mode == "count_down":
        play_order = [r for r in available_ranks if r <= starting_rank][::-1]
    elif mode == "random":
        play_order = [r for r in available_ranks if r >= starting_rank]
        random.shuffle(play_order)
    else:
        return {"error": f"Invalid mode: {mode}"}

    # --- Spotify client + helpers
    sp = get_spotify_user_client()

    def _pick_device_id():
        try:
            devices = sp.devices().get("devices", [])
            if not devices:
                logger.error("No Spotify devices. Open the Spotify app and play something once to activate.")
                return None
            active = next((d for d in devices if d.get("is_active")), None)
            chosen = active or devices[0]
            logger.info(f"Using device: {chosen.get('name')} ({chosen.get('id')}) active={chosen.get('is_active')}")
            return chosen.get("id")
        except Exception as e:
            logger.exception(f"Failed to list devices: {e}")
            return None

    def _set_volume(vol: int, device_id: str):
        vol = max(0, min(100, int(vol)))
        try:
            sp.volume(vol, device_id=device_id)
            logger.debug(f"volume -> {vol}")
        except Exception as e:
            logger.exception(f"volume failed -> {vol}: {e}")

    def _start_track(track_id: str, device_id: str, position_ms: int = 0) -> bool:
        try:
            sp.start_playback(
                device_id=device_id,
                uris=[f"spotify:track:{track_id}"],
                position_ms=position_ms,
            )
            logger.info(f"▶ start_playback track={track_id} pos={position_ms}ms")
            return True
        except Exception as e:
            logger.exception(f"start_playback failed for track={track_id}: {e}")
            return False

    device_id = _pick_device_id()
    if not device_id:
        return {"error": "No active Spotify device. Open Spotify and play any track once, then try again."}

    # Explicitly activate the target device so volume calls won't 404/NO_ACTIVE_DEVICE
    try:
        sp.transfer_playback(device_id=device_id, force_play=False)
        logger.debug("transfer_playback OK")
    except Exception as e:
        logger.warning(f"transfer_playback failed (continuing): {e}")

    results = []

    for rank in play_order:
        ranking = next((rk for rk in rankings if rk.ranking == rank), None)
        if not ranking:
            continue

        track = db.get(Track, ranking.track_id)
        if not track:
            logger.warning(f"Missing Track for ranking {rank}")
            continue
        artist = db.get(Artist, track.artist_id)

        intro_mp3 = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02}.mp3"
        detail_mp3 = f"{track.spotify_track_id}.mp3"
        artist_mp3 = f"{artist.spotify_artist_id}.mp3" if artist and artist.spotify_artist_id else None

        logger.info("=" * 90)
        logger.info(f"▶ Rank #{rank} | {track.track_name} by {artist.artist_name}")

        # --- Log intro/detail/artist text to terminal (mirrors what we'll play)
        intro_text = getattr(ranking, "intro", None) or getattr(track, "intro", None)
        detail_text = getattr(ranking, "detail", None) or getattr(track, "detail", None)
        artist_text = (
            getattr(artist, "artist_description", None)
            or getattr(artist, "description", None)
            or getattr(artist, "bio", None)
        )
        if play_intro and intro_text:
            logger.info("📣 INTRO TEXT:",intro_text)
        if play_detail and detail_text:
            logger.info("📝 DETAIL TEXT:", detail_text)
        if play_artist_mp3 and artist_text:
            logger.info("👤 ARTIST TEXT:", artist_text)

        # --- Start bed track (if configured) ---
        if SPOTIFY_BED_TRACK_ID:
            # Start bed first (activates device), then set volume down
            if _start_track(SPOTIFY_BED_TRACK_ID, device_id):
                await asyncio.sleep(0.6)
                _set_volume(int(100 * BED_FACTOR), device_id)

        # --- Play narration MP3s (these do not affect Spotify device) ---
        if play_intro:
            await play_mp3(BUCKET_TRACK_INTRO, intro_mp3)
        if play_detail:
            await play_mp3(BUCKET_TRACK_DETAIL, detail_mp3)
        if play_artist_mp3 and artist_mp3:
            await play_mp3(BUCKET_ARTIST, artist_mp3)

        # --- Play main track (do NOT pause bed; starting main replaces it) ---
        if play_track:
            if _start_track(track.spotify_track_id, device_id):
                _set_volume(100, device_id)  # restore volume
                await asyncio.sleep(60)      # play main for 1 minute

        results.append({"rank": rank, "track": track.track_name, "artist": artist.artist_name})

    return {
        "status": "completed",
        "mode": mode,
        "starting_rank": starting_rank,
        "tracks_played": results
    }
