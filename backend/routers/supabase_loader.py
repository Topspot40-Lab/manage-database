# backend/routers/supabase_loader.py
from __future__ import annotations

# NEW for mobile playback UI / signed URLs
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
import json


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

from backend.services.narration_bundle import urls_for_rank_dg as _urls_for_rank


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
# Load (decade, genre) data and store context — UPDATED
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/load-decade-genre-data")
def load_decade_genre_data(
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
            return {
                "decade": decade, "genre": genre, "language": lang,
                "track_count": 0, "rankings": [], "message": "No rankings found."
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

            # Try to load the canonical artist row (may be None for various imports)
            artist = None
            artist_name_for_output = None
            if getattr(track, "artist_id", None):
                artist = db.get(Artist, track.artist_id)
                artist_name_for_output = getattr(artist, "artist_name", None)

            # ✅ display-name fallback chain (great for DUETs)
            artist_name_for_output = (
                artist_name_for_output
                or getattr(track, "artist_display_name", None)
                or getattr(track, "artist_name", None)
                or "Unknown Artist"
            )

            # Build media keys (guard artist None)
            intro_filename  = build_intro_filename(decade, genre, r.ranking)
            detail_filename = build_detail_filename(track.spotify_track_id)
            artist_filename = (
                build_artist_filename(artist.spotify_artist_id)
                if artist and getattr(artist, "spotify_artist_id", None)
                else None
            )

            # Localized text
            intro_text, detail_text = get_localized_texts(db, lang, r, track)

            # ── New TV/Source fields (with legacy fallbacks) ───────────────────
            source_type  = getattr(track, "source_type", None)
            source_title = (
                getattr(track, "source_title", None)
                or getattr(track, "show_name", None)        # legacy JSON field
            )
            years_on_air = (
                getattr(track, "years_on_air", None)
                or getattr(track, "year_on_air", None)      # legacy JSON field
            )
            source_role  = (
                getattr(track, "source_role", None)
                or getattr(track, "show_genre", None)       # legacy JSON field
            )
            version_notes = getattr(track, "version_notes", None)

            # If we see any TV-ish fields but no explicit type, default to TV
            if not source_type and (source_title or years_on_air or source_role):
                source_type = "TV"

            response.append({
                "rank": r.ranking,
                "trackName": track.track_name,
                # use the computed display-name chain
                "artistName": artist_name_for_output,
                "modeFlag": getattr(getattr(track, "mode_flag", None), "value", getattr(track, "mode_flag", None)),
                "intro": intro_text,
                "detail": detail_text,
                "artistDescription": getattr(artist, "artist_description", None) if artist else None,

                # S3 / object keys
                "introKey":  {"bucket": intro_bucket,  "key": key_for("intro",  intro_filename)},
                "detailKey": {"bucket": detail_bucket, "key": key_for("detail", detail_filename)} if detail_filename else None,
                "artistKey": {"bucket": artist_bucket, "key": key_for("artist", artist_filename)} if artist_filename else None,

                # Images
                "artistArtwork": getattr(artist, "artist_artwork", None) if artist else None,
                "albumArtwork": track.album_artwork,

                # NEW: source/TV fields in the payload
                "sourceType": source_type,
                "sourceTitle": source_title,
                "yearsOnAir": years_on_air,
                "sourceRole": source_role,
                "versionNotes": version_notes,
            })

        logger.info("✅ Loaded %d ranked tracks for %s / %s (lang=%s)", len(response), decade, genre, lang)
        return {
            "decade": decade, "genre": genre, "language": lang,
            "track_count": len(response),
            "rankings": sorted(response, key=lambda x: x["rank"])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("load_decade_genre_data failed")
        return {"error": "load_decade_genre_data failed", "detail": f"{type(e).__name__}: {e!s}"}

# ─────────────────────────────────────────────────────────────────────────────
# Play a sequence starting from a rank (localized)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/play-tracks-with-starting-rank", response_class=HTMLResponse)
async def play_tracks_with_starting_rank(
    request: Request,
    starting_rank: int = Query(...),
    mode: Literal["count_up","count_down","random"] = Query("count_up"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(False),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    ui: int = Query(1, description="1 = HTML player (mobile/browser). 0 = JSON bundle."),
    server: bool = Query(True, description="True = server-side playback like before; ignores ui."),
    expires: int = Query(300, ge=60, le=3600),
    db: Session = Depends(get_db)
):
    lang = normalize_language_code_canon(tts_language)

    decade = current_decade_genre.get("decade")
    genre  = current_decade_genre.get("genre")
    if not decade or not genre:
        err = {"error": "No context. Use /supabase/load-decade-genre-data first."}
        return JSONResponse(err, status_code=400)

    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return JSONResponse({"error": f"No DecadeGenre found for {decade} / {genre}"}, status_code=404)

    rows = db.exec(select(TrackRanking).where(TrackRanking.decade_genre_id == dg.id)).all()
    if not rows:
        return JSONResponse({"error": "No rankings found for this combo."}, status_code=404)

    # Build play order
    max_rank = max(r.ranking for r in rows)
    order = list(range(1, max_rank+1))
    if mode == "count_up":
        play_order = [r for r in order if r >= starting_rank]
    elif mode == "count_down":
        play_order = [r for r in order if r <= starting_rank][::-1]
    else:
        import random
        play_order = [r for r in order if r >= starting_rank]; random.shuffle(play_order)

    # ─────────────────────────────────────────────
    # SERVER MODE (old behavior): play on desktop
    # ─────────────────────────────────────────────
    if server:
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

            # 3) Bed + narrations (played on the SERVER machine)
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
                    return JSONResponse({"status": "skipped", "mode": mode, "language": lang, "tracks_played": results})

            results.append({"rank": rk, "track": track.track_name})

        return JSONResponse({"status": "completed", "mode": mode, "language": lang, "tracks_played": results})

    # ─────────────────────────────────────────────
    # BROWSER MODE (mobile/desktop HTML or JSON)
    # ─────────────────────────────────────────────
    # Build client-side sequence of narration URLs + spotify ids
    sequence = []
    for rk in play_order:
        bundle, err = _urls_for_rank(
            db, lang, decade, genre, rk,
            use_intro=play_intro, use_detail=play_detail, use_artist=play_artist_description,
            expires=expires, request=request
        )
        if err:
            logger.warning("Skipping rank %s: %s", rk, err)
            continue
        sequence.append(bundle)

    base = str(request.base_url).rstrip("/")

    if ui == 0:
        return JSONResponse({
            "decade": decade, "genre": genre, "mode": mode, "language": lang,
            "play_track": play_track, "expires": expires,
            "sequence": sequence
        })

    # Minimal HTML player (tap/click Start to play MP3 on device, then Spotify)
    html = f"""<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>TopSpot: {decade} / {genre} ({mode})</title>
<style>
 body{{font:16px/1.5 system-ui,Segoe UI,Roboto,Arial;background:#0b0b0c;color:#e6e6e6;max-width:760px;margin:24px auto;padding:0 14px}}
 button{{font:inherit;padding:10px 14px;border-radius:12px;border:0;background:#2b6;cursor:pointer}}
 button[disabled]{{opacity:.5;cursor:not-allowed}}
 .muted{{color:#9aa}}
 .row{{margin:.5rem 0}}
 .badge{{display:inline-block;background:#222;border:1px solid #333;border-radius:10px;padding:2px 8px;margin-right:6px}}
 .log{{white-space:pre-wrap;background:#111;border:1px solid #222;border-radius:12px;padding:10px;margin-top:12px;max-height:40vh;overflow:auto}}
</style>
<h2>TopSpot Player — {decade} / {genre}</h2>
<p class="muted">Mode: <b>{mode}</b> • Language: <b>{lang}</b></p>
<div class="row"><button id="go">▶ Start</button> <span id="status" class="badge">idle</span></div>
<ol id="list"></ol>
<div class="log" id="log"></div>
<script>
const seq = {json.dumps(sequence)};
const decade = {json.dumps(decade)};
const genre  = {json.dumps(genre)};
const lang   = {json.dumps(lang)};
const base   = {json.dumps(base)};
const playTrack = {json.dumps(play_track)};

const elList = document.getElementById('list');
const elStatus = document.getElementById('status');
const elLog = document.getElementById('log');
function log(msg){{ elLog.textContent += msg + "\\n"; elLog.scrollTop = elLog.scrollHeight; }}
function setStatus(s){{ elStatus.textContent = s; }}

seq.forEach(step => {{
  const li = document.createElement('li');
  li.textContent = `#${{step.rank}} — ${{step.track_name}} — ${{step.artist_name||""}}`;
  elList.appendChild(li);
}});

function playOne(url) {{
  return new Promise((resolve, reject) => {{
    const a = new Audio(url);
    a.preload = "auto";
    a.onended = () => resolve();
    a.onerror = () => reject(new Error("Audio error: " + url));
    a.play().catch(reject);
  }});
}}

async function playNarrations(step) {{
  const urls = [];
  if (Array.isArray(step.intros)) urls.push(...step.intros);
  if (step.detail) urls.push(step.detail);
  if (step.artist) urls.push(step.artist);
  for (const u of urls) {{
    setStatus("narration");
    log("▶ " + u);
    try {{ await playOne(u); }} catch(e) {{ log("skip: " + e.message); }}
  }}
}}

async function startSpotify(rank, spotifyId) {{
  setStatus("spotify");
  const qs = new URLSearchParams({{
    decade, genre, rank,
    play_intro: "false",
    play_detail: "false",
    play_artist_description: "false",
    play_track: "true",
    tts_language: lang
  }});
  const url = `${{base}}/supabase/play-track-by-rank?${{qs.toString()}}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error("Spotify play failed: " + r.status);
}}

document.getElementById('go').onclick = async () => {{
  const btn = document.getElementById('go');
  btn.disabled = true;
  try {{
    for (const step of seq) {{
      await playNarrations(step);
      if (playTrack && step.spotify_track_id) {{
        await startSpotify(step.rank, step.spotify_track_id);
        setStatus("waiting");
      }}
    }}
    setStatus("done");
  }} catch (e) {{
    console.error(e); log("ERROR: " + e.message); setStatus("error");
  }} finally {{
    btn.disabled = false;
  }}
}};
</script>
"""
    return HTMLResponse(html)
