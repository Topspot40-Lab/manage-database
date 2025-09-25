# backend/routers/supabase_loader.py
from __future__ import annotations

from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Literal
from sqlmodel import Session, select

import asyncio
import logging
from backend.utils.naming import normalize_language_code_canon

from sqlmodel import Session as SQLSession
from sqlalchemy.exc import OperationalError, InterfaceError
from backend.models.dbmodels import TrackRanking, Track, Artist
from backend.services.localization import get_localized_texts
from backend.database import get_db, engine

from backend.state import current_decade_genre, skip_event

from backend.services.db_queries import get_decade_genre, get_rankings_for_combo
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename
)

# NEW modular helpers
from backend.services.radio_pick import fetch_random_pick

# Centralized policy helpers
from backend.config.volume import PLAY_FULL_TRACK
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs, narration_keys_for,
    maybe_play_bed, play_narrations, play_track_with_skip
)

logger = logging.getLogger(__name__)  # -> "backend.routers.supabase_loader"
router = APIRouter(prefix="/supabase", tags=["Supabase"])

# ─────────────────────────────────────────────────────────────────────────────
# Random track: pick from DB, narrate, then play
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/play-random-track-from-db")
async def play_random_track_from_db(
    play_intro: bool = Query(True, description="Play intro MP3(s) if available"),
    play_detail: bool = Query(True, description="Play detail MP3 if available"),
    play_artist_description: bool = Query(True, description="Play artist description MP3 if available"),
    play_track: bool = Query(True, description="Play the Spotify track"),
    num_tracks: int = Query(1, description="How many random tracks to play (-1 = keep playing forever)"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
):
    lang = normalize_language_code_canon(tts_language)
    played: list[dict] = []
    count = 0

    async def _play_one() -> dict | None:
        # DB pick (short-lived session + one retry)
        with SQLSession(engine) as s:
            try:
                pick = fetch_random_pick(s)
            except (OperationalError, InterfaceError) as e:
                logger.warning("DB connection dropped; retrying once: %s", e)
                try:
                    s.rollback()
                except Exception:
                    pass
                pick = fetch_random_pick(s)

        if not pick:
            logger.warning("No playable tracks found (need spotify_track_id != NULL).")
            return None

        track, artist, tr_rows = pick.track, pick.artist, pick.rankings

        # 1) Header + text logs
        log_header_and_texts(lang=lang, track=track, artist=artist, tr_rows=tr_rows)

        # 2) Narration assets
        intro_jobs = build_intro_jobs(lang=lang, tr_rows=tr_rows) if play_intro else []
        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)

        # 3) Bed + narrations
        if (play_intro and intro_jobs) or (play_detail and detail_bucket and detail_key) or (play_artist_description and artist_bucket and artist_key):
            await maybe_play_bed()
        await play_narrations(
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist=play_artist_description,
            intro_jobs=intro_jobs,
            detail_bucket=detail_bucket, detail_key=detail_key,
            artist_bucket=artist_bucket, artist_key=artist_key
        )

        # 4) Main track
        try:
            skipped_mid = False
            if play_track and track.spotify_track_id:
                skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
                if skipped_mid:
                    logger.info("⏭️ Skip triggered during track playback.")
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
            "modeFlag": getattr(getattr(track, "mode_flag", None), "value", getattr(track, "mode_flag", None)),
            "skipped": skipped_mid,
        }

    while True:
        if num_tracks != -1 and count >= num_tracks:
            break
        if skip_event.is_set():
            skip_event.clear()
            break

        try:
            res = await _play_one()
        except (OperationalError, InterfaceError) as e:
            logger.warning("DB connection lost; retrying: %s", e)
            await asyncio.sleep(2)
            continue

        if res:
            played.append(res)
            count += 1
            if res.get("skipped"):
                break

        await asyncio.sleep(0.3)

    return {"status": "ok", "language": lang, "played_count": len(played), "played": played}

# ─────────────────────────────────────────────────────────────────────────────
# Skip current track (external stop)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/skip-current-track")
async def skip_current_track():
    skip_event.set()
    return {"status": "skipping"}

# ─────────────────────────────────────────────────────────────────────────────
# Play by rank within currently loaded decade/genre
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/play-track-by-rank-only")
async def play_track_by_rank_only(
    rank: int = Query(..., description="Rank of the track to play"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
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

# ─────────────────────────────────────────────────────────────────────────────
# Play by rank (explicit decade/genre) — with localization
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/play-track-by-rank")
async def play_track_by_rank(
    decade: str = Query(..., description="e.g., 1980s"),
    genre: str  = Query(..., description="e.g., pop"),
    rank: int   = Query(..., description="Rank to play"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    db: Session = Depends(get_db)
):
    lang = normalize_language_code_canon(tts_language)

    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return {"error": f"No DecadeGenre found for {decade} / {genre}"}

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

    # 1) Logs/texts
    log_header_and_texts(lang=lang, track=track, artist=artist, tr_rows=[(rk, decade, genre)])

    # 2) Narration assets
    intro_jobs = build_intro_jobs(lang=lang, tr_rows=[(rk, decade, genre)]) if play_intro else []
    detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)

    # 3) Bed + narrations
    if (play_intro and intro_jobs) or (play_detail and detail_bucket and detail_key) or (play_artist_description and artist_bucket and artist_key):
        await maybe_play_bed()
    await play_narrations(
        play_intro=play_intro, play_detail=play_detail, play_artist=play_artist_description,
        intro_jobs=intro_jobs,
        detail_bucket=detail_bucket, detail_key=detail_key,
        artist_bucket=artist_bucket, artist_key=artist_key
    )

    # 4) Main track
    if play_track and track.spotify_track_id:
        skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
        if skipped_mid:
            logger.info("⏭️ Skip triggered during track playback.")
            return {
                "status": "skipped",
                "decade": decade, "genre": genre, "rank": rank,
                "played": {"intro": play_intro, "detail": play_detail, "track": play_track,
                           "artist": play_artist_description}
            }

    return {
        "status": "success",
        "decade": decade, "genre": genre, "rank": rank,
        "played": {"intro": play_intro, "detail": play_detail, "track": play_track, "artist": play_artist_description}
    }

# ─────────────────────────────────────────────────────────────────────────────
# Load (decade, genre) data and store context
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/load-decade-genre-data")
def load_deacade_genre_data(
    decade: str = Query(..., description="Decade name, e.g., '1980s'"),
    genre: str = Query(..., description="Genre name, e.g., 'country'"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    db: Session = Depends(get_db)
):
    try:
        current_decade_genre["decade"] = decade
        current_decade_genre["genre"]  = genre
        lang = normalize_language_code_canon(tts_language)
        logger.info("📌 Stored context for play-by-rank-only: %s / %s (lang=%s)", decade, genre, lang)

        dg = get_decade_genre(db, decade, genre)
        if not dg:
            raise HTTPException(status_code=404, detail=f"No DecadeGenre found for {decade} / {genre}")

        rankings = get_rankings_for_combo(db, dg.id)
        if not rankings:
            return {"decade": decade, "genre": genre, "language": lang, "track_count": 0, "rankings": [], "message": "No rankings found."}

        intro_bucket  = bucket_for(lang, "intro")
        detail_bucket = bucket_for(lang, "detail")
        artist_bucket = bucket_for(lang, "artist")

        response = []
        for r in rankings:
            track = db.get(Track, r.track_id)
            if not track:
                logger.warning("⚠️ Track ID %s not found", r.track_id); continue
            artist = db.get(Artist, track.artist_id)
            if not artist:
                logger.warning("⚠️ Artist ID %s not found", track.artist_id); continue

            intro_filename  = build_intro_filename(decade, genre, r.ranking)
            detail_filename = build_detail_filename(track.spotify_track_id)
            artist_filename = build_artist_filename(artist.spotify_artist_id) if artist.spotify_artist_id else None

            intro_text, detail_text = get_localized_texts(db, lang, r, track)

            response.append({
                "rank": r.ranking,
                "trackName": track.track_name,
                "artistName": artist.artist_name,
                "modeFlag": getattr(getattr(track, "mode_flag", None), "value", getattr(track, "mode_flag", None)),
                "intro": intro_text,
                "detail": detail_text,
                "artistDescription": getattr(artist, "artist_description", None),
                "introKey":  {"bucket": intro_bucket,  "key": key_for("intro",  intro_filename)},
                "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)} if detail_filename else None,
                "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,
                "artistArtwork": artist.artist_artwork,
                "albumArtwork": track.album_artwork
            })

        logger.info("✅ Loaded %d ranked tracks for %s / %s (lang=%s)", len(response), decade, genre, lang)
        return {"decade": decade, "genre": genre, "language": lang, "track_count": len(response), "rankings": sorted(response, key=lambda x: x["rank"])}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("load_decade_genre_data failed")
        return {"error": "load_decade_genre_data failed", "detail": f"{type(e).__name__}: {e!s}"}

# ─────────────────────────────────────────────────────────────────────────────
# Play a sequence starting from a rank (localized)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/play-tracks-with-starting-rank")
async def play_tracks_with_starting_rank(
    starting_rank: int = Query(...),
    mode: Literal["count_up","count_down","random"] = Query("count_up"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    db: Session = Depends(get_db)
):
    lang = normalize_language_code_canon(tts_language)

    decade = current_decade_genre.get("decade")
    genre  = current_decade_genre.get("genre")
    if not decade or not genre:
        return {"error": "No context. Use /supabase/load-decade-genre-data first."}

    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return {"error": f"No DecadeGenre found for {decade} / {genre}"}

    rows = db.exec(select(TrackRanking).where(TrackRanking.decade_genre_id == dg.id)).all()
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

    results = []
    for rk in play_order:
        r = next((x for x in rows if x.ranking == rk), None)
        if not r:
            continue
        track  = db.get(Track, r.track_id)
        artist = db.get(Artist, track.artist_id) if track else None
        if not track or not artist:
            continue

        # 1) Logs/texts
        log_header_and_texts(lang=lang, track=track, artist=artist, tr_rows=[(r, decade, genre)])

        # 2) Narration assets
        intro_jobs = build_intro_jobs(lang=lang, tr_rows=[(r, decade, genre)]) if play_intro else []
        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)

        # 3) Bed + narrations
        if (play_intro and intro_jobs) or (play_detail and detail_bucket and detail_key) or (play_artist_description and artist_bucket and artist_key):
            await maybe_play_bed()
        await play_narrations(
            play_intro=play_intro, play_detail=play_detail, play_artist=play_artist_description,
            intro_jobs=intro_jobs,
            detail_bucket=detail_bucket, detail_key=detail_key,
            artist_bucket=artist_bucket, artist_key=artist_key
        )

        # 4) Main track
        if play_track and track.spotify_track_id:
            skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
            if skipped_mid:
                logger.info("⏭️ Skip triggered during sequence playback.")
                results.append({"rank": rk, "track": track.track_name, "skipped": True})
                return {"status": "skipped", "mode": mode, "language": lang, "tracks_played": results}

        results.append({"rank": rk, "track": track.track_name})

    return {"status": "completed", "mode": mode, "language": lang, "tracks_played": results}
