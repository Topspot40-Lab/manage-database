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

from backend.services.spotify.playback import play_spotify_track
from backend.state import current_decade_genre, skip_event
from backend.config import SPOTIFY_BED_TRACK_ID

from backend.services.db_queries import (
    get_decade_genre, get_rankings_for_combo,
)
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename,
    safe_play
)

# NEW modular helpers
from backend.services.radio_pick import fetch_random_pick
from backend.services.radio_render import (
    render_header, box, clean_text, BOX_WIDTH
)

from backend.config.volume import (
    PLAY_FULL_TRACK,
    TRACK_PLAY_SECONDS as CFG_TRACK_PLAY_SECONDS,
    FULL_TRACK_FALLBACK_SECONDS,
    MAX_FULL_TRACK_SECONDS,
)


logger = logging.getLogger(__name__)  # -> "backend.routers.supabase_loader"
router = APIRouter(prefix="/supabase", tags=["Supabase"])

def _compute_play_seconds(track) -> int:
    """
    Decide how long to let Spotify play before we move on,
    using the controls from backend/config/volume.py.
    """
    try:
        if PLAY_FULL_TRACK:
            # Prefer track.duration_ms if present; fall back if missing.
            ms = getattr(track, "duration_ms", None)
            secs = (ms / 1000.0) if ms else float(FULL_TRACK_FALLBACK_SECONDS)
            # Safety cap so "full" never blocks forever
            secs = min(secs, float(MAX_FULL_TRACK_SECONDS))
        else:
            secs = float(CFG_TRACK_PLAY_SECONDS)
        # Be defensive: never less than 1 second
        return max(1, int(round(secs)))
    except Exception:
        # Last-resort fallback: don't explode on bad data; use configured fixed seconds
        return max(1, int(round(float(CFG_TRACK_PLAY_SECONDS))))

async def _sleep_with_skip(total_seconds: int, chunk: float = 0.2) -> bool:
    """
    Sleep up to total_seconds, but return early if skip_event is set.
    Returns True if a skip was triggered, False if full sleep completed.
    """
    remaining = float(total_seconds)
    while remaining > 0:
        if skip_event.is_set():
            skip_event.clear()
            return True
        to_sleep = chunk if remaining > chunk else remaining
        await asyncio.sleep(to_sleep)
        remaining -= to_sleep
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Random track: pick from DB, narrate, then play
# (kept EN-only text display; MP3s are still language-bucketed)
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
    lang = normalize_language_code_canon(tts_language)  # -> 'en' | 'es' | 'pt-BR'
    print("play_random_track_from_db")  # quick breadcrumb

    async def _maybe_play_bed():
        if not SPOTIFY_BED_TRACK_ID:
            return
        try:
            play_spotify_track(SPOTIFY_BED_TRACK_ID)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning("Bed track failed: %s", e)

    async def _play_one() -> dict | None:
        # Open/close DB session quickly, before any sleeps.
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

        track = pick.track
        artist = pick.artist
        tr_rows = pick.rankings

        # 1) Header (clean, conditional)
        header_text = render_header(
            track_name=track.track_name,
            artist_name=artist.artist_name,
            track_id=track.spotify_track_id,
            lang=lang,
            tr_rows=tr_rows or [],
        )
        logger.info("\n%s", header_text)

        # 2) Pretty print the DETAIL and ARTIST text blocks after header (localized)
        if tr_rows:
            first_rk = tr_rows[0][0]
            with SQLSession(engine) as s_loc:
                intro_text_loc, detail_text_loc = get_localized_texts(s_loc, lang, first_rk, track)
        else:
            intro_text_loc, detail_text_loc = None, None

        # 👇 Add this log right here
        logger.info(
            f"[intro:{lang} {'OK' if intro_text_loc else 'FALLBACK'}] "
            f"[detail:{lang} {'OK' if (detail_text_loc and lang == 'pt-BR') else 'FALLBACK/EN'}]"



        )

        if intro_text_loc:
            logger.info(box("INTRO", clean_text(intro_text_loc), width=BOX_WIDTH))

        detail_text = clean_text(detail_text_loc) if detail_text_loc else clean_text(track.detail)
        if detail_text:
            logger.info(box("DETAIL", detail_text, width=BOX_WIDTH))

        artist_text = clean_text(getattr(artist, "artist_description", None))
        if artist_text:
            logger.info(box("ARTIST", artist_text, width=BOX_WIDTH))

        # 3) Build intros to play (and collect file names)
        intro_jobs = []
        if play_intro and tr_rows:
            for tr, decade_name, genre_name in tr_rows:
                intro_filename = build_intro_filename(decade_name, genre_name, tr.ranking)
                intro_key = key_for("intro", intro_filename)
                intro_bucket = bucket_for(lang, "intro")
                intro_jobs.append((intro_bucket, intro_key, decade_name, genre_name, tr.ranking))

        # 4) Detail + artist narration keys
        detail_filename = build_detail_filename(track.spotify_track_id)
        detail_key      = key_for("detail", detail_filename) if detail_filename else None
        detail_bucket   = bucket_for(lang, "detail") if detail_filename else None

        artist_filename = build_artist_filename(artist.spotify_artist_id)
        artist_key      = key_for("artist", artist_filename) if artist_filename else None
        artist_bucket   = bucket_for(lang, "artist") if artist_filename else None

        # 5) Bed under narrations
        await _maybe_play_bed()

        # 6) Play all intros (sequential)
        if play_intro and intro_jobs:
            for bkt, key, d, g, rk in intro_jobs:
                await safe_play("Intro", bkt, key)

        # 7) Play detail + artist description MP3s
        if play_detail and detail_bucket and detail_key:
            await safe_play("Detail", detail_bucket, detail_key)
        if play_artist_description and artist_bucket and artist_key:
            await safe_play("Artist", artist_bucket, artist_key)

        # 8) Play the track (no DB session held during sleep)
        try:
            if play_track and track.spotify_track_id:
                play_secs = _compute_play_seconds(track)
                logger.info("🎵 Now playing track: %s (%s) for %ss (full=%s)",
                            track.track_name, track.spotify_track_id, play_secs, PLAY_FULL_TRACK)
                play_spotify_track(track.spotify_track_id)
                skipped_mid = await _sleep_with_skip(play_secs)
                if skipped_mid:
                    logger.info("⏭️ Skip triggered during track playback.")
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
                        "modeFlag": getattr(getattr(track, "mode_flag", None), "value",
                                            getattr(track, "mode_flag", None)),
                        "skipped": True,
                    }


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

        }

    played: list[dict] = []
    count = 0
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

        if res and res.get("skipped"):
            break

        count += 1
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
    lang = normalize_language_code_canon(tts_language)  # -> 'en' | 'es' | 'pt-BR'

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

    # Build filenames/keys/buckets for the SELECTED language
    intro_fn   = build_intro_filename(decade, genre, rank)
    detail_fn  = build_detail_filename(track.spotify_track_id)
    artist_fn  = build_artist_filename(artist.spotify_artist_id)

    intro_key  = key_for("intro",  intro_fn)
    detail_key = key_for("detail", detail_fn) if detail_fn else None
    artist_key = key_for("artist", artist_fn) if artist_fn else None

    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail") if detail_key else None
    artist_bucket = bucket_for(lang, "artist") if artist_key else None

    # 1) Show texts FIRST (localized when es/ptbr; fallback to EN)
    intro_txt, detail_txt = get_localized_texts(db, lang, rk, track)

    # 👇 Add this log right here
    logger.info(
        f"[intro:{lang} {'OK' if intro_txt else 'FALLBACK'}] "
        f"[detail:{lang} {'OK' if (detail_txt and lang == 'pt-BR') else 'FALLBACK/EN'}]"
    )

    if intro_txt:
        logger.info(box("INTRO", clean_text(intro_txt), width=BOX_WIDTH))
    if detail_txt:
        logger.info(box("DETAIL", clean_text(detail_txt), width=BOX_WIDTH))

    if getattr(artist, "artist_description", None):
        logger.info(box("ARTIST", clean_text(artist.artist_description), width=BOX_WIDTH))

    # 2) Bed under the narration
    if SPOTIFY_BED_TRACK_ID and (play_intro or play_detail or play_artist_description):
        try:
            play_spotify_track(SPOTIFY_BED_TRACK_ID)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning("Bed track failed: %s", e)

    # 3) Play MP3s from the SELECTED language
    if play_intro:
        await safe_play("Intro", intro_bucket, intro_key)
    if play_detail and detail_bucket and detail_key:
        await safe_play("Detail", detail_bucket, detail_key)
    if play_artist_description and artist_bucket and artist_key:
        await safe_play("Artist", artist_bucket, artist_key)

    # 4) Main track
    if play_track and track.spotify_track_id:
        play_secs = _compute_play_seconds(track)
        logger.info("🎵 Now playing track: %s (%s) for %ss (full=%s)",
                    track.track_name, track.spotify_track_id, play_secs, PLAY_FULL_TRACK)
        play_spotify_track(track.spotify_track_id)
        skipped_mid = await _sleep_with_skip(play_secs)
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
def load_deacade_genre_data(  # (spelling preserved if other code calls this)
    decade: str = Query(..., description="Decade name, e.g., '1980s'"),
    genre: str = Query(..., description="Genre name, e.g., 'country'"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),


    db: Session = Depends(get_db)
):
    try:
        current_decade_genre["decade"] = decade
        current_decade_genre["genre"]  = genre
        lang = normalize_language_code_canon(tts_language)  # -> 'en' | 'es' | 'pt-BR'
        logger.info("📌 Stored context for play-by-rank-only: %s / %s (lang=%s)", decade, genre, lang)

        dg = get_decade_genre(db, decade, genre)
        if not dg:
            raise HTTPException(status_code=404, detail=f"No DecadeGenre found for {decade} / {genre}")

        rankings = get_rankings_for_combo(db, dg.id)
        if not rankings:
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

            intro_text, detail_text = get_localized_texts(db, lang, r, track)

            response.append({
                "rank": r.ranking,
                "trackName": track.track_name,
                "artistName": artist.artist_name,
                "modeFlag": getattr(getattr(track, "mode_flag", None), "value", getattr(track, "mode_flag", None)),
                "intro": intro_text,
                "detail": detail_text,
                "artistDescription": getattr(artist, "artist_description", None),
                "introKey": {"bucket": intro_bucket, "key": key_for("intro", intro_filename)},
                "detailKey": {"bucket": detail_bucket,
                              "key": key_for("detail", detail_filename)} if detail_filename else None,
                "artistKey": {"bucket": artist_bucket,
                              "key": key_for("artist", artist_filename)} if artist_filename else None,
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
        raise
    except Exception as e:
        logger.exception("load_decade_genre_data failed")
        return {
            "error": "load_decade_genre_data failed",
            "detail": f"{type(e).__name__}: {e!s}"
        }


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
    lang = normalize_language_code_canon(tts_language)  # -> 'en' | 'es' | 'pt-BR'

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

    results = []

    for rk in play_order:
        r = next((x for x in rows if x.ranking == rk), None)
        if not r:
            continue
        track  = db.get(Track, r.track_id)
        artist = db.get(Artist, track.artist_id) if track else None
        if not track or not artist:
            continue

        intro_fn   = build_intro_filename(decade, genre, rk)
        detail_fn  = build_detail_filename(track.spotify_track_id)
        artist_fn  = build_artist_filename(artist.spotify_artist_id)

        intro_key  = key_for("intro",  intro_fn)
        detail_key = key_for("detail", detail_fn) if detail_fn else None
        artist_key = key_for("artist", artist_fn) if artist_fn else None

        intro_bucket  = bucket_for(lang, "intro")
        detail_bucket = bucket_for(lang, "detail") if detail_key else None
        artist_bucket = bucket_for(lang, "artist") if artist_key else None

        # 1) Localized texts FIRST
        intro_txt, detail_txt = get_localized_texts(db, lang, r, track)

        # 👇 Add this log right here
        logger.info(
            f"[intro:{lang} {'OK' if intro_txt else 'FALLBACK'}] "
            f"[detail:{lang} {'OK' if (detail_txt and lang == 'pt-BR') else 'FALLBACK/EN'}]"
        )

        if intro_txt:
            logger.info(box("INTRO", clean_text(intro_txt), width=BOX_WIDTH))
        if detail_txt:
            logger.info(box("DETAIL", clean_text(detail_txt), width=BOX_WIDTH))

        if getattr(artist, "artist_description", None):
            logger.info(box("ARTIST", clean_text(artist.artist_description), width=BOX_WIDTH))

        # 2) Bed under narration
        if SPOTIFY_BED_TRACK_ID and (play_intro or play_detail or play_artist_description):
            try:
                play_spotify_track(SPOTIFY_BED_TRACK_ID)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning("Bed track failed: %s", e)

        # 3) Play MP3s in the SELECTED language
        if play_intro:
            await safe_play("Intro", intro_bucket, intro_key)
        if play_detail and detail_bucket and detail_key:
            await safe_play("Detail", detail_bucket, detail_key)
        if play_artist_description and artist_bucket and artist_key:
            await safe_play("Artist", artist_bucket, artist_key)

        # 4) Main track
        if play_track and track.spotify_track_id:
            play_secs = _compute_play_seconds(track)
            logger.info("🎵 Now playing track: %s (%s) for %ss (full=%s)",
                        track.track_name, track.spotify_track_id, play_secs, PLAY_FULL_TRACK)
            play_spotify_track(track.spotify_track_id)
            skipped_mid = await _sleep_with_skip(play_secs)
            if skipped_mid:
                logger.info("⏭️ Skip triggered during sequence playback.")
                results.append({"rank": rk, "track": track.track_name, "skipped": True})
                return {"status": "skipped", "mode": mode, "language": lang, "tracks_played": results}

        results.append({"rank": rk, "track": track.track_name})

    return {"status": "completed", "mode": mode, "language": lang, "tracks_played": results}
