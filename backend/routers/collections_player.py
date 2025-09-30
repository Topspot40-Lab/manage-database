# backend/routers/collections_player.py
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import Session, select

from backend.database import get_db
from backend.utils.naming import normalize_language_code_canon
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track, Artist

# server-side playback helpers you already have
from backend.services.radio_runtime import (
    narration_keys_for,
    maybe_play_bed, play_narrations, play_track_with_skip,
    # collection-aware logger:
    log_collection_header_and_texts,
)

# bucket resolver for language-aware audio buckets (audio-en, audio-es, etc.)
from backend.services.playback_helpers import bucket_for

from backend.config.volume import PLAY_FULL_TRACK

# centralized bundler for signed URLs / spotify ids (now includes collection intros)
from backend.services.narration_bundle import urls_for_rank_collection

router = APIRouter(prefix="/supabase/collections", tags=["Collections"])


def collection_intro_jobs(*, lang: str, slug: str, rank: int):
    """
    Build server-side intro job list for collections:
    uses bucket audio-<lang>, key collections-intro/{slug}_{rank:02d}.mp3
    Tuple shape matches what play_narrations expects.
    """
    bucket = bucket_for(lang, "intro")  # e.g., audio-en, audio-es, audio-ptbr
    key = f"collections-intro/{slug}_{rank:02d}.mp3"
    return [(bucket, key, "collection", slug, rank)]


@router.get("/play-track-by-rank")
async def play_track_by_rank(
    collection_slug: str = Query(...),
    rank: int = Query(...),
    play_intro: bool = Query(True),                 # NEW: allow server-side intro playback
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en","es","ptbr","pt-BR"] = Query("en"),
    db: Session = Depends(get_db),
):
    lang = normalize_language_code_canon(tts_language)
    coll = db.exec(select(Collection).where(Collection.slug == collection_slug)).first()
    if not coll:
        return {"error": f"No Collection for {collection_slug!r}"}

    ctr = db.exec(select(CollectionTrackRanking).where(
        CollectionTrackRanking.collection_id == coll.id,
        CollectionTrackRanking.ranking == rank
    )).first()
    if not ctr:
        return {"error": f"No ranking #{rank} in collection {collection_slug}"}

    track = db.get(Track, ctr.track_id)
    artist = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return {"error": "Track or Artist not found"}

    # ✅ Collection-aware logs (shows collection name + slug) and prints CTR.intro box
    log_collection_header_and_texts(lang=lang, collection=coll, ctr=ctr, track=track, artist=artist)

    # Narration assets
    detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)

    # ✅ Collection intro mp3 job(s)
    intro_jobs = collection_intro_jobs(lang=lang, slug=coll.slug, rank=rank) if play_intro else []

    # Play narrations server-side
    if intro_jobs or (play_detail and detail_bucket and detail_key) or (play_artist_description and artist_bucket and artist_key):
        await maybe_play_bed()
    await play_narrations(
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist=play_artist_description,
        intro_jobs=intro_jobs,
        detail_bucket=detail_bucket, detail_key=detail_key,
        artist_bucket=artist_bucket, artist_key=artist_key
    )

    # Main track (Spotify)
    if play_track and track.spotify_track_id:
        skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
        if skipped_mid:
            return {"status": "skipped", "collection": collection_slug, "rank": rank}

    return {"status": "success", "collection": collection_slug, "rank": rank}


@router.get("/play-sequence", response_class=HTMLResponse)
async def play_sequence(
    request: Request,
    collection_slug: str = Query(...),
    starting_rank: int = Query(...),
    mode: Literal["count_up","count_down","random"] = Query("count_up"),
    play_intro: bool = Query(True),                 # NEW: include collection intro
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en","es","ptbr","pt-BR"] = Query("en"),
    ui: int = Query(1, description="1=HTML player (mobile/browser). 0=JSON bundle."),
    server: bool = Query(True, description="True=server-side playback like decade/genre."),
    expires: int = Query(300, ge=60, le=3600),
    db: Session = Depends(get_db),
):
    lang = normalize_language_code_canon(tts_language)
    coll = db.exec(select(Collection).where(Collection.slug == collection_slug)).first()
    if not coll:
        return JSONResponse({"error": f"No Collection for {collection_slug!r}"}, status_code=404)

    rows = db.exec(select(CollectionTrackRanking).where(
        CollectionTrackRanking.collection_id == coll.id
    )).all()
    if not rows:
        return JSONResponse({"error": "No rankings for this collection."}, status_code=404)

    max_rank = max(r.ranking for r in rows)
    order = list(range(1, max_rank + 1))
    if mode == "count_up":
        play_order = [r for r in order if r >= starting_rank]
    elif mode == "count_down":
        play_order = [r for r in order if r <= starting_rank][::-1]
    else:
        import random
        play_order = [r for r in order if r >= starting_rank]
        random.shuffle(play_order)

    # SERVER mode: narrate + play on server (✅ now includes collection intro)
    if server:
        results = []
        for rk in play_order:
            r = next((x for x in rows if x.ranking == rk), None)
            if not r:
                continue
            track = db.get(Track, r.track_id)
            artist = db.get(Artist, track.artist_id) if track else None
            if not track or not artist:
                continue

            # ✅ Collection-aware header + shows CTR.intro text
            log_collection_header_and_texts(lang=lang, collection=coll, ctr=r, track=track, artist=artist)

            # narration keys + optional collection intro job(s)
            detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)
            intro_jobs = collection_intro_jobs(lang=lang, slug=coll.slug, rank=rk) if play_intro else []

            if intro_jobs or (play_detail and detail_bucket and detail_key) or (play_artist_description and artist_bucket and artist_key):
                await maybe_play_bed()
            await play_narrations(
                play_intro=play_intro,
                play_detail=play_detail,
                play_artist=play_artist_description,
                intro_jobs=intro_jobs,
                detail_bucket=detail_bucket, detail_key=detail_key,
                artist_bucket=artist_bucket, artist_key=artist_key
            )

            # spotify
            if play_track and track.spotify_track_id:
                skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
                if skipped_mid:
                    results.append({"rank": rk, "track": track.track_name, "skipped": True})
                    return JSONResponse({"status": "skipped", "collection": collection_slug, "mode": mode, "language": lang, "tracks_played": results})

            results.append({"rank": rk, "track": track.track_name})

        return JSONResponse({"status": "completed", "collection": collection_slug, "mode": mode, "language": lang, "tracks_played": results})

    # BROWSER mode: build client bundle of signed URLs + spotify ids (now includes collection intro if enabled)
    sequence = []
    for rk in play_order:
        bundle, err = urls_for_rank_collection(
            db=db,
            lang=lang,
            collection_id=coll.id,
            rank=rk,
            use_intro=play_intro,                # ✅ include intro when requested
            use_detail=play_detail,
            use_artist=play_artist_description,
            expires=expires,
            request=request,
            collection_slug=coll.slug,          # pass slug so filenames resolve
        )
        if err or not bundle:
            continue
        sequence.append({"rank": rk, **bundle})

    base = str(request.base_url).rstrip("/")
    if ui == 0:
        return JSONResponse({
            "collection": collection_slug,
            "mode": mode,
            "language": lang,
            "play_track": play_track,
            "expires": expires,
            "sequence": sequence
        })

    html = f"""<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>TopSpot: Collection {collection_slug} ({mode})</title>
<style>
 body{{font:16px/1.5 system-ui,Segoe UI,Roboto,Arial;background:#0b0b0c;color:#e6e6e6;max-width:760px;margin:24px auto;padding:0 14px}}
 button{{font:inherit;padding:10px 14px;border-radius:12px;border:0;background:#2b6;cursor:pointer}}
 button[disabled]{{opacity:.5;cursor:not-allowed}}
 .muted{{color:#9aa}} .row{{margin:.5rem 0}}
 .badge{{display:inline-block;background:#222;border:1px solid #333;border-radius:10px;padding:2px 8px;margin-right:6px}}
 .log{{white-space:pre-wrap;background:#111;border:1px solid #222;border-radius:12px;padding:10px;margin-top:12px;max-height:40vh;overflow:auto}}
</style>
<h2>TopSpot — Collection: {collection_slug}</h2>
<p class="muted">Mode: <b>{mode}</b> • Language: <b>{lang}</b></p>
<div class="row"><button id="go">▶ Start</button> <span id="status" class="badge">idle</span></div>
<ol id="list"></ol>
<div class="log" id="log"></div>
<script>
const seq = {json.dumps(sequence)};
const base = {json.dumps(base)};
const lang = {json.dumps(lang)};
const playTrack = {json.dumps(play_track)};
const extra = {json.dumps({"collection_slug": collection_slug})};

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
    setStatus("narration"); log("▶ " + u);
    try {{ await playOne(u); }} catch(e) {{ log("skip: " + e.message); }}
  }}
}}

async function startSpotify(rank, spotifyId) {{
  setStatus("spotify");
  const qs = new URLSearchParams({{ ...extra, rank,
    play_detail: "false", play_artist_description: "false", play_track: "true", tts_language: lang, play_intro: "false" }});
  const url = `${{base}}/supabase/collections/play-track-by-rank?${{qs.toString()}}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error("Spotify play failed: " + r.status);
}}

document.getElementById('go').onclick = async () => {{
  const btn = document.getElementById('go'); btn.disabled = true;
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

