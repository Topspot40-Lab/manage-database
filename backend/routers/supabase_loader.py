# backend/routers/supabase_loader.py

from fastapi import APIRouter, Query, Depends
from typing import Literal
from sqlmodel import Session, select
from backend.database import get_db
from backend.models import TrackRanking, Track, Artist, Decade, Genre, DecadeGenre
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.spotify.playback import play_spotify_track
from backend.state import current_decade_genre, skip_event
from backend.config import BED_VOLUME_PERCENT, BUCKETS, AUDIO_PREFIXES
import logging

router = APIRouter(prefix="/supabase", tags=["Supabase"])
logger = logging.getLogger("supabase_loader")

# --- helpers for language-aware buckets/keys ---
def _canon_lang(code: str) -> str:
    m = (code or "en").strip().lower()
    return {"en": "en", "es": "es", "ptbr": "pt-BR"}.get(m, "en")

def _bucket_for(language: str, kind: Literal["intro", "detail", "artist"]) -> str:
    lang = _canon_lang(language)
    return BUCKETS.get(lang, BUCKETS["en"])[kind]

def _key_for(kind: Literal["intro", "detail", "artist"], filename: str) -> str:
    return f"{AUDIO_PREFIXES[kind]}/{filename}"

@router.post("/skip-current-track")
async def skip_current_track():
    skip_event.set()
    return {"status": "skipping"}

@router.get("/play-track-by-rank-only")
async def play_track_by_rank_only(
    rank: int = Query(..., description="Rank of the track to play"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_mp3: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
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
        tts_language=tts_language,
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
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    from backend.services.supabase_playback import play_mp3

    lang = _canon_lang(tts_language)
    logger.info(f"🎯 Playing track by rank: {decade} / {genre} / #{rank} (lang={lang})")

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

    # === Filenames (unchanged) ===
    intro_filename  = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02}.mp3"
    detail_filename = f"{track.spotify_track_id}.mp3"
    artist_filename = f"{artist.spotify_artist_id}.mp3"

    # === Keys (prefix folders) ===
    intro_key  = _key_for("intro", intro_filename)
    detail_key = _key_for("detail", detail_filename)
    artist_key = _key_for("artist", artist_filename)

    # === Buckets (per language) ===
    intro_bucket  = _bucket_for(lang, "intro")
    detail_bucket = _bucket_for(lang, "detail")
    artist_bucket = _bucket_for(lang, "artist")

    logger.info("=" * 90)
    logger.info(
        f"🎯 {decade} / {genre} — Rank #{rank} | 🎵 {track.track_name} by {artist.artist_name} | lang={lang}"
    )

    # === Playback ===
    if play_intro:
        if ranking.intro:
            logger.info(f"\n📢 Intro Text (→ {intro_key} in {intro_bucket}):\n{ranking.intro.strip()}")
        await play_mp3(intro_bucket, intro_key)

    if play_detail:
        if track.detail:
            logger.info(f"\n📝 Detail Text (→ {detail_key} in {detail_bucket}):\n{track.detail.strip()}")
        await play_mp3(detail_bucket, detail_key)

    if play_artist_mp3:
        if artist.artist_description:
            logger.info(f"\n🎙️ Artist Description (→ {artist_key} in {artist_bucket}):\n{artist.artist_description.strip()}")
        await play_mp3(artist_bucket, artist_key)

    # === Log Artwork URLs After Playback Starts ===
    logger.info(f"🖼️ Artist Artwork: {artist.artist_artwork or '[None]'}")
    logger.info(f"💿 Album Artwork: {track.album_artwork or '[None]'}")

    if play_track:
        logger.debug(f"🎵 Playing track on Spotify: {track.spotify_track_id}")
        play_spotify_track(track.spotify_track_id)

    return {
        "status": "success",
        "language": lang,
        "track": track.track_name,
        "artist": artist.artist_name,
        "played": {"intro": play_intro, "detail": play_detail, "track": play_track, "artist": play_artist_mp3},
        "keys": {
            "intro":  {"bucket": intro_bucket,  "key": intro_key},
            "detail": {"bucket": detail_bucket, "key": detail_key},
            "artist": {"bucket": artist_bucket, "key": artist_key},
        },
    }

@router.get("/load-decade-genre-data")
def load_decade_genre_data(
    decade: str = Query(..., description="Decade name, e.g., '1980s'"),
    genre: str = Query(..., description="Genre name, e.g., 'country'"),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    # ✅ Remember the context
    current_decade_genre["decade"] = decade
    current_decade_genre["genre"] = genre
    lang = _canon_lang(tts_language)
    logger.info(f"📌 Stored context for play-by-rank-only: {decade} / {genre} (lang={lang})")

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

    intro_bucket  = _bucket_for(lang, "intro")
    detail_bucket = _bucket_for(lang, "detail")
    artist_bucket = _bucket_for(lang, "artist")

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

        intro_filename  = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank_entry.ranking:02}.mp3"
        detail_filename = f"{track.spotify_track_id}.mp3"
        artist_filename = f"{artist.spotify_artist_id}.mp3" if artist.spotify_artist_id else None

        response.append({
            "rank": rank_entry.ranking,
            "trackName": track.track_name,
            "artistName": artist.artist_name,
            "intro": getattr(rank_entry, "intro", None) or getattr(track, "intro", None),
            "detail": getattr(rank_entry, "detail", None) or getattr(track, "detail", None),
            "artistDescription": getattr(artist, "artist_description", None) or getattr(artist, "description", None) or getattr(artist, "bio", None),
            # filenames (legacy)
            "introMp3": intro_filename,
            "detailMp3": detail_filename,
            "artistMp3": artist_filename,
            # language-aware bucket + prefixed keys (new)
            "introKey":  {"bucket": intro_bucket,  "key": _key_for("intro", intro_filename)},
            "detailKey": {"bucket": detail_bucket, "key": _key_for("detail", detail_filename)},
            "artistKey": {"bucket": artist_bucket, "key": _key_for("artist", artist_filename)} if artist_filename else None,
            "artistArtwork": artist.artist_artwork,
            "albumArtwork": track.album_artwork
        })

    logger.info(f"✅ Loaded {len(response)} ranked tracks for {decade} / {genre} (lang={lang})")
    return {
        "decade": decade,
        "genre": genre,
        "language": lang,
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
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    import random, asyncio
    from sqlmodel import select
    from backend.config import SPOTIFY_BED_TRACK_ID
    from backend.services.supabase_playback import play_mp3
    from backend.services.spotify.spotify_auth_user import get_spotify_user_client
    from backend.models import Decade, Genre, DecadeGenre, TrackRanking, Track, Artist
    from backend.state import current_decade_genre

    lang = _canon_lang(tts_language)

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
            logger.debug(f"▶ start_playback track={track_id} pos={position_ms}ms")
            return True
        except Exception as e:
            logger.exception(f"start_playback failed for track={track_id}: {e}")
            return False

    device_id = _pick_device_id()
    if not device_id:
        return {"error": "No active Spotify device. Open Spotify and play any track once, then try again."}

    try:
        sp.transfer_playback(device_id=device_id, force_play=False)
        logger.debug("transfer_playback OK")
    except Exception as e:
        logger.warning(f"transfer_playback failed (continuing): {e}")

    results = []

    intro_bucket  = _bucket_for(lang, "intro")
    detail_bucket = _bucket_for(lang, "detail")
    artist_bucket = _bucket_for(lang, "artist")

    for rank in play_order:
        ranking = next((rk for rk in rankings if rk.ranking == rank), None)
        if not ranking:
            continue

        track = db.get(Track, ranking.track_id)
        if not track:
            logger.warning(f"Missing Track for ranking {rank}")
            continue
        artist = db.get(Artist, track.artist_id)

        intro_filename  = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02}.mp3"
        detail_filename = f"{track.spotify_track_id}.mp3"
        artist_filename = f"{artist.spotify_artist_id}.mp3" if artist and artist.spotify_artist_id else None

        intro_key  = _key_for("intro", intro_filename)
        detail_key = _key_for("detail", detail_filename)
        artist_key = _key_for("artist", artist_filename) if artist_filename else None

        logger.info("=" * 90)
        logger.info(f"▶ Rank #{rank} | {track.track_name} by {artist.artist_name} (lang={lang})")

        # Log texts (what we’ll play)
        intro_text = getattr(ranking, "intro", None) or getattr(track, "intro", None)
        detail_text = getattr(ranking, "detail", None) or getattr(track, "detail", None)
        artist_text = (
            getattr(artist, "artist_description", None)
            or getattr(artist, "description", None)
            or getattr(artist, "bio", None)
        )
        if play_intro and intro_text:
            logger.info("📣 INTRO TEXT:\n%s", intro_text)
        if play_detail and detail_text:
            logger.info("📝 DETAIL TEXT:\n%s", detail_text)
        if play_artist_mp3 and artist_text:
            logger.info("👤 ARTIST TEXT:\n%s", artist_text)

        # --- Start bed track (if configured) ---
        if SPOTIFY_BED_TRACK_ID:
            if _start_track(SPOTIFY_BED_TRACK_ID, device_id):
                await asyncio.sleep(0.6)
                _set_volume(BED_VOLUME_PERCENT, device_id)

        # --- Play narration MP3s ---
        if play_intro:
            await play_mp3(intro_bucket, intro_key)
        if play_detail:
            await play_mp3(detail_bucket, detail_key)
        if play_artist_mp3 and artist_key:
            await play_mp3(artist_bucket, artist_key)

        # --- Play main track ---
        if play_track:
            if _start_track(track.spotify_track_id, device_id):
                _set_volume(100, device_id)
                await asyncio.sleep(60)

        results.append({"rank": rank, "track": track.track_name, "artist": artist.artist_name})

    return {
        "status": "completed",
        "mode": mode,
        "language": lang,
        "starting_rank": starting_rank,
        "tracks_played": results
    }
