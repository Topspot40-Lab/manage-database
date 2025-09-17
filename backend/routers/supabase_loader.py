# backend/routers/supabase_loader.py
from fastapi import APIRouter, Query, Depends
from typing import Literal
from sqlmodel import Session, select
from backend.database import get_db
from backend.models.dbmodels import TrackRanking, Track, Artist
from backend.services.spotify.playback import play_spotify_track
from backend.state import current_decade_genre, skip_event
from backend.config import SPOTIFY_BED_TRACK_ID

from backend.services.db_queries import (
    get_decade_genre, get_rankings_for_combo, get_random_track,
    get_rankings_for_track, get_artist_by_id
)
from backend.services.playback_helpers import (
    canon_lang, bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename,
    log_narration_texts, safe_play   # ⬅️ add this
)

import asyncio
import logging

logger = logging.getLogger(__name__)  # -> "backend.routers.supabase_loader"
logger.info("hello from supabase_loader, level=%s", logger.getEffectiveLevel())
router = APIRouter(prefix="/supabase", tags=["Supabase"])

logger.info(
    "logger name=%s effective=%s",
    logger.name,
    logging.getLevelName(logger.getEffectiveLevel()),
)
# ─────────────────────────────────────────────────────────────────────────────
# existing endpoints (skip-current-track, load-decade-genre-data, etc.)
# NOTE: keep your current ones; below we show only the NEW endpoint for brevity
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/play-random-track-from-db")
async def play_random_track_from_db(
    play_intro: bool = Query(True, description="Play intro MP3(s) if available"),
    play_detail: bool = Query(True, description="Play detail MP3 if available"),
    play_artist_description: bool = Query(True, description="Play artist description MP3 if available"),
    play_track: bool = Query(True, description="Play the Spotify track for 60 seconds"),
    num_tracks: int = Query(1, description="How many random tracks to play (-1 = keep playing forever)"),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    """
    Pick a random Track and:
      - play ALL matching intros (if multiple TrackRanking rows exist for the track_id),
      - play the detail MP3 and artist description MP3 if requested,
      - then play the Spotify track for ~60s.

    num_tracks:
      - 1..N : plays that many tracks, then returns
      - -1   : loops forever (request won't return unless cancelled)
    """
    lang = canon_lang(tts_language)

    async def _maybe_play_bed():
        if not SPOTIFY_BED_TRACK_ID:
            return
        try:
            play_spotify_track(SPOTIFY_BED_TRACK_ID)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning("Bed track failed: %s", e)

    async def _play_one() -> dict | None:
        # 1) Random track
        track = get_random_track(db)
        if not track:
            logger.warning("No playable tracks found (need spotify_track_id != NULL).")
            return None

        artist = get_artist_by_id(db, track.artist_id)
        if not artist:
            logger.warning("Artist id=%s not found.", track.artist_id)
            return None
        # 2) All intros for this track_id
        tr_rows = get_rankings_for_track(db, track.id)  # [(TrackRanking, decade, genre), ...]

        # Pretty headers
        decades = ", ".join(sorted({d for (_, d, _) in tr_rows})) if tr_rows else "—"
        genres = ", ".join(sorted({g for (_, _, g) in tr_rows})) if tr_rows else "—"

        # Prefer the rank for the *active* decade/genre if you know them; else fallback
        # Replace `active_decade_name` / `active_genre_name` with your current context vars if available.
        active_decade_name = None  # e.g., decade.decade_name
        active_genre_name = None  # e.g., genre.genre_name

        rank_val = next(
            (tr.ranking for (tr, d, g) in tr_rows
             if active_decade_name and active_genre_name and d == active_decade_name and g == active_genre_name),
            None
        )

        if rank_val is None and tr_rows:
            # If only one unique ranking exists across all decade/genre pairs, use it; else mark as multiple
            unique_ranks = {tr.ranking for (tr, _, _) in tr_rows}
            rank_val = next(iter(unique_ranks)) if len(unique_ranks) == 1 else None

        rank_str = f"#{rank_val}" if rank_val is not None else "multiple" if tr_rows and len(tr_rows) > 1 else "—"




        logger.info(
            "===================================================\n"
            "RANDOM TRACK PICK\n"
            "Rank: %s  Decade: %s\tGenre: %s\n"
            "Title: %s\tArtist: %s\n"
            "track_id: %s\tlang: %s\n"
            "===================================================",
            rank_str,
            decades,
            genres,
            track.track_name,
            artist.artist_name,
            (track.spotify_track_id or track.id),
            lang,
        )

        # ────────────────────────────────────────────────────────────────────────────

        intro_jobs, intro_texts, intro_files = [], [], []
        if play_intro and tr_rows:
            for tr, decade_name, genre_name in tr_rows:
                intro_filename = build_intro_filename(decade_name, genre_name, tr.ranking)
                intro_key = key_for("intro", intro_filename)
                intro_bucket = bucket_for(lang, "intro")

                intro_files.append(intro_filename)
                if tr.intro:
                    intro_texts.append((decade_name, genre_name, tr.ranking, tr.intro))
                intro_jobs.append((intro_bucket, intro_key, decade_name, genre_name, tr.ranking))
        # 3) Detail + artist narration keys
        detail_filename = build_detail_filename(track.spotify_track_id)
        detail_key      = key_for("detail", detail_filename) if detail_filename else None
        detail_bucket   = bucket_for(lang, "detail") if detail_filename else None

        artist_filename = build_artist_filename(artist.spotify_artist_id)
        artist_key      = key_for("artist", artist_filename) if artist_filename else None
        artist_bucket   = bucket_for(lang, "artist") if artist_filename else None

        # 4) Log texts to terminal
        intro_text_joined = "\n\n".join(
            [f"[{d}/{g} #{rk:02}] {txt.strip()}" for (d, g, rk, txt) in intro_texts]
        ) if intro_texts else None

        # right before log_narration_texts(...)
        intro_file_display = ", ".join(intro_files) if intro_files else None

        log_narration_texts(
            intro=intro_text_joined,
            detail=(track.detail or None),
            artist=(artist.artist_description or None),
            intro_file=intro_file_display,  # ⬅️ show all intro mp3s, if multiple
            detail_file=detail_filename,  # ⬅️ single detail mp3
            artist_file=artist_filename,  # ⬅️ single artist mp3
        )

        # 5) Bed under narrations
        await _maybe_play_bed()
        # 6) Play all intros (sequential)
        if play_intro and intro_jobs:
            for bkt, key, d, g, rk in intro_jobs:
                # logger.info("▶ Intro: %s / %s  #%02d  (%s)", d, g, rk, key)
                await safe_play("Intro", bkt, key)

        # 7) Play detail + artist description MP3s
        if play_detail and detail_bucket and detail_key:
            # logger.info("▶ Detail MP3: %s", detail_key)
            await safe_play("Detail", detail_bucket, detail_key)

        if play_artist_description and artist_bucket and artist_key:
            # logger.info("▶ Artist MP3: %s", artist_key)
            await safe_play("Artist", artist_bucket, artist_key)

        # 8) Play the track for 60 seconds
        try:
            if play_track and track.spotify_track_id:
                logger.info("🎵 Now playing track: %s (%s) for 60s", track.track_name, track.spotify_track_id)
                play_spotify_track(track.spotify_track_id)
                await asyncio.sleep(60)
        except Exception as e:
            logger.exception("Failed to play track: %s", e)

        return {
            "track": {
                "id": track.id,
                "name": track.track_name,
                "spotify_track_id": track.spotify_track_id,
            },
            "artist": {
                "id": artist.id,
                "name": artist.artist_name,
                "spotify_artist_id": artist.spotify_artist_id,
            },
            "intros_played": [{"decade": d, "genre": g, "rank": rk} for (_, _, d, g, rk) in intro_jobs],
            "detail_played": bool(play_detail and detail_bucket and detail_key),
            "artist_played": bool(play_artist_description and artist_bucket and artist_key),
        }

    played: list[dict] = []
    count = 0
    while True:
        # stop if finite
        if num_tracks != -1 and count >= num_tracks:
            break
        # optional: allow external stop via /skip-current-track
        if skip_event.is_set():
            skip_event.clear()
            break

        res = await _play_one()
        if res:
            played.append(res)
        count += 1

        # small gap between tracks (optional)
        await asyncio.sleep(0.3)

    return {"status": "ok", "language": lang, "played_count": len(played), "played": played}

# ⬇️ Add BELOW your existing imports and router definition in
# backend/routers/supabase_loader.py

# --- keep the random endpoint you added ---

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
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    decade = current_decade_genre.get("decade")
    genre  = current_decade_genre.get("genre")
    if not decade or not genre:
        return {"error": "No track data loaded. Use /supabase/load-decade-genre-data first."}
    return await play_track_by_rank(
        decade=decade, genre=genre, rank=rank,
        play_intro=play_intro, play_detail=play_detail,
        play_track=play_track, play_artist_description=play_artist_description,
        tts_language=tts_language, db=db
    )

@router.get("/play-track-by-rank")
async def play_track_by_rank(
    decade: str = Query(..., description="e.g., 1980s"),
    genre: str  = Query(..., description="e.g., pop"),
    rank: int   = Query(..., description="Rank to play"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    lang = canon_lang(tts_language)

    # Resolve (decade, genre) -> decade_genre_id
    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return {"error": f"No DecadeGenre found for {decade} / {genre}"}

    # Find ranking row for the rank
    rk = db.exec(
        select(TrackRanking).where(
            TrackRanking.decade_genre_id == dg.id,
            TrackRanking.ranking == rank
        )
    ).first()
    if not rk:
        return {"error": f"No ranking #{rank} in {decade}/{genre}"}

    track  = db.get(Track, rk.track_id)
    artist = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return {"error": "Track or Artist not found"}

    # Build filenames/keys/buckets
    intro_fn   = build_intro_filename(decade, genre, rank)
    detail_fn  = build_detail_filename(track.spotify_track_id)
    artist_fn  = build_artist_filename(artist.spotify_artist_id)

    intro_key  = key_for("intro",  intro_fn)
    detail_key = key_for("detail", detail_fn) if detail_fn else None
    artist_key = key_for("artist", artist_fn) if artist_fn else None

    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail") if detail_key else None
    artist_bucket = bucket_for(lang, "artist") if artist_key else None

    # Log/print texts (include filenames)
    log_narration_texts(
        intro=rk.intro,  # TrackRanking
        detail=track.detail,  # Track
        artist=getattr(artist, "artist_description", None),
        intro_file=intro_fn,
        detail_file=detail_fn,
        artist_file=artist_fn,
    )

    # Playback narration MP3s (safe)
    if play_intro:
        await safe_play("Intro", intro_bucket, intro_key)
    if play_detail and detail_bucket and detail_key:
        await safe_play("Detail", detail_bucket, detail_key)
    if play_artist_description and artist_bucket and artist_key:
        await safe_play("Artist", artist_bucket, artist_key)

    # Main track (60s)
    if play_track and track.spotify_track_id:
        play_spotify_track(track.spotify_track_id)
        await asyncio.sleep(60)

    return {
        "status": "success",
        "decade": decade, "genre": genre, "rank": rank,
        "played": {"intro": play_intro, "detail": play_detail, "track": play_track, "artist": play_artist_description}
    }

from fastapi import HTTPException

@router.get("/load-decade-genre-data")
def load_decade_genre_data(
    decade: str = Query(..., description="Decade name, e.g., '1980s'"),
    genre: str = Query(..., description="Genre name, e.g., 'country'"),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    try:
        # ✅ Remember the context
        current_decade_genre["decade"] = decade
        current_decade_genre["genre"] = genre
        lang = canon_lang(tts_language)
        logger.info("📌 Stored context for play-by-rank-only: %s / %s (lang=%s)", decade, genre, lang)

        # Resolve DecadeGenre
        logger.debug("DBG before get_decade_genre(%s, %s)", decade, genre)
        dg = get_decade_genre(db, decade, genre)
        logger.debug("DBG after get_decade_genre: dg.id=%s", getattr(dg, "id", None))
        if not dg:
            # Prefer a 404 over silent error dict for APIs
            raise HTTPException(status_code=404, detail=f"No DecadeGenre found for {decade} / {genre}")

        # Get rankings for this combo
        logger.debug("DBG before get_rankings_for_combo(%s)", dg.id)
        rankings = get_rankings_for_combo(db, dg.id)
        logger.debug("DBG after get_rankings_for_combo: n=%s", 0 if rankings is None else len(rankings))

        if not rankings:
            # Return a friendly, successful empty payload
            return {
                "decade": decade,
                "genre": genre,
                "language": lang,
                "track_count": 0,
                "rankings": [],
                "message": "No rankings found."
            }

        intro_bucket  = bucket_for(lang, "intro")
        detail_bucket = bucket_for(lang, "detail")
        artist_bucket = bucket_for(lang, "artist")

        response = []
        for r in rankings:
            track = db.get(Track, r.track_id)
            if not track:
                logger.warning("⚠️ Track ID %s not found", r.track_id)
                continue

            artist = db.get(Artist, track.artist_id)
            if not artist:
                logger.warning("⚠️ Artist ID %s not found", track.artist_id)
                continue

            intro_filename  = build_intro_filename(decade, genre, r.ranking)
            detail_filename = build_detail_filename(track.spotify_track_id)
            artist_filename = build_artist_filename(artist.spotify_artist_id) if artist.spotify_artist_id else None

            response.append({
                "rank": r.ranking,
                "trackName": track.track_name,
                "artistName": artist.artist_name,
                "intro": r.intro,                       # ← from TrackRanking
                "detail": track.detail,                 # ← from Track
                "artistDescription": getattr(artist, "artist_description", None),
                "introKey":  {"bucket": intro_bucket,  "key": key_for("intro",  intro_filename)},
                "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)} if detail_filename else None,
                "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,
                "artistArtwork": artist.artist_artwork,
                "albumArtwork": track.album_artwork
            })

        logger.info("✅ Loaded %d ranked tracks for %s / %s (lang=%s)", len(response), decade, genre, lang)
        return {
            "decade": decade,
            "genre": genre,
            "language": lang,
            "track_count": len(response),
            "rankings": sorted(response, key=lambda x: x["rank"])
        }

    except HTTPException:
        # Let FastAPI return the proper status code + detail
        raise
    except Exception as e:
        # Log full traceback to server logs and surface message to caller (TEMP for debugging)
        logger.exception("load_decade_genre_data failed")
        return {
            "error": "load_decade_genre_data failed",
            "detail": f"{type(e).__name__}: {e!s}"
        }

@router.get("/play-tracks-with-starting-rank")
async def play_tracks_with_starting_rank(
    starting_rank: int = Query(...),
    mode: Literal["count_up","count_down","random"] = Query("count_up"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr"] = Query("en"),
    db: Session = Depends(get_db)
):
    lang   = canon_lang(tts_language)
    decade = current_decade_genre.get("decade")
    genre  = current_decade_genre.get("genre")
    if not decade or not genre:
        return {"error": "No context. Use /supabase/load-decade-genre-data first."}

    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return {"error": f"No DecadeGenre found for {decade} / {genre}"}

    rows = db.exec(
        select(TrackRanking).where(TrackRanking.decade_genre_id == dg.id)
    ).all()
    if not rows:
        return {"error": "No rankings found for this combo."}

    max_rank = max(r.ranking for r in rows)
    order = list(range(1, max_rank+1))
    if mode == "count_up":
        play_order = [r for r in order if r >= starting_rank]
    elif mode == "count_down":
        play_order = [r for r in order if r <= starting_rank][::-1]
    else:
        import random
        play_order = [r for r in order if r >= starting_rank]; random.shuffle(play_order)

    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail")
    artist_bucket = bucket_for(lang, "artist")

    results = []
    for rk in play_order:
        r = next((x for x in rows if x.ranking == rk), None)
        if not r: continue
        track  = db.get(Track, r.track_id)
        artist = db.get(Artist, track.artist_id) if track else None
        if not track or not artist: continue

        intro_fn   = build_intro_filename(decade, genre, rk)
        detail_fn  = build_detail_filename(track.spotify_track_id)
        artist_fn  = build_artist_filename(artist.spotify_artist_id)

        # Log narration text to terminal (include filenames)
        log_narration_texts(
            intro=r.intro,  # TrackRanking.intro
            detail=track.detail,  # Track.detail
            artist=getattr(artist, "artist_description", None),
            intro_file=intro_fn,
            detail_file=detail_fn,
            artist_file=artist_fn,
        )

        # Start a soft bed under the narration (main track will replace it)
        if SPOTIFY_BED_TRACK_ID and (play_intro or play_detail or play_artist_description):
            try:
                play_spotify_track(SPOTIFY_BED_TRACK_ID)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning("Bed track failed: %s", e)

        # Narration MP3s (safe)
        if play_intro:
            await safe_play("Intro", intro_bucket, key_for("intro", intro_fn))
        if play_detail and detail_fn:
            await safe_play("Detail", detail_bucket, key_for("detail", detail_fn))
        if play_artist_description and artist_fn:
            await safe_play("Artist", artist_bucket, key_for("artist", artist_fn))

        # Main track for 60s (this replaces the bed automatically)
        if play_track and track.spotify_track_id:
            play_spotify_track(track.spotify_track_id)
            await asyncio.sleep(60)

        results.append({"rank": rk, "track": track.track_name})

    return {"status": "completed", "mode": mode, "language": lang, "tracks_played": results}
