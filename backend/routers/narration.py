from __future__ import annotations
from fastapi import APIRouter, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Literal
import logging

from sqlmodel import Session, select
from backend.database import get_db
from backend.models.dbmodels import TrackRanking, Track, Artist
from backend.utils.naming import normalize_language_code_canon
from backend.services.db_queries import get_decade_genre
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename,
)
from backend.services.supabase_signer import sign_url
# from backend.security.api_key import require_key   # uncomment to protect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/narration", tags=["Narration"])  # , dependencies=[Depends(require_key)])

@router.get("/urls-by-rank")
def urls_by_rank(
    decade: str = Query(...),
    genre: str  = Query(...),
    rank: int   = Query(...),
    tts_language: Literal["en","es","ptbr","pt-BR"] = Query("en"),
    expires: int = Query(300, ge=60, le=3600),
    db: Session = Depends(get_db),
):
    lang = normalize_language_code_canon(tts_language)
    dg = get_decade_genre(db, decade, genre)
    if not dg:
        return JSONResponse({"error": f"No DecadeGenre for {decade}/{genre}"}, status_code=404)

    rk = db.exec(select(TrackRanking).where(
        TrackRanking.decade_genre_id == dg.id,
        TrackRanking.ranking == rank
    )).first()
    if not rk:
        return JSONResponse({"error": f"No ranking #{rank} in {decade}/{genre}"}, status_code=404)

    track  = db.get(Track, rk.track_id)
    artist = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return JSONResponse({"error": "Track or Artist not found"}, status_code=404)

    intro_fn   = build_intro_filename(decade, genre, rank)
    detail_fn  = build_detail_filename(track.spotify_track_id)
    artist_fn  = build_artist_filename(artist.spotify_artist_id)

    intro_key  = key_for("intro",  intro_fn)
    detail_key = key_for("detail", detail_fn) if detail_fn else None
    artist_key = key_for("artist", artist_fn) if artist_fn else None

    intro_bucket  = bucket_for(lang, "intro")
    detail_bucket = bucket_for(lang, "detail") if detail_key else None
    artist_bucket = bucket_for(lang, "artist") if artist_key else None

    payload = {
        "decade": decade, "genre": genre, "rank": rank,
        "spotify_track_id": track.spotify_track_id,
        "intros": [],
        "detail": None,
        "artist": None,
    }

    intro_url  = sign_url(intro_bucket,  intro_key,  expires)
    detail_url = sign_url(detail_bucket, detail_key, expires) if (detail_bucket and detail_key) else None
    artist_url = sign_url(artist_bucket, artist_key, expires) if (artist_bucket and artist_key) else None

    if intro_url:  payload["intros"].append(intro_url)
    if detail_url: payload["detail"] = detail_url
    if artist_url: payload["artist"] = artist_url
    return payload

@router.get("/player", response_class=HTMLResponse)
def narration_player():
    # Plays narration clips locally on the phone, then calls play-track-by-rank with narrations off.
    return HTMLResponse("""<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>TopSpot Narration Player</title>
<style>
 body{font:16px/1.4 system-ui,Segoe UI,Roboto,Arial;max-width:720px;margin:20px auto;padding:0 12px;background:#0b0b0c;color:#e6e6e6}
 button{font:inherit;padding:10px 14px;border-radius:10px}
 code{background:#222;padding:2px 4px;border-radius:4px}
 .muted{color:#9aa}
</style>
<h2>TopSpot Narration Player</h2>
<p class="muted">Plays narration on this device, then starts the Spotify track here.</p>
<p><b>Tap Start</b> (mobile browsers require a user gesture).</p>
<div id="status"></div>
<p><button id="go">▶ Start</button></p>
<script>
(async () => {
  const qs = new URLSearchParams(location.search);
  const base = location.origin;
  const decade = qs.get("decade");
  const genre  = qs.get("genre");
  const rank   = qs.get("rank");
  const lang   = qs.get("tts_language") || "en";
  const apikey = qs.get("key"); // optionally forward X-API-Key
  const headers = apikey ? { "X-API-Key": apikey } : {};
  const status = (m)=>document.getElementById('status').innerText = m;

  if (!decade || !genre || !rank) {
    status("Missing query. Example: ?decade=1970s&genre=Latin%20Global&rank=1&tts_language=es");
    return;
  }

  async function bundle(){
    const u = `${base}/narration/urls-by-rank?decade=${encodeURIComponent(decade)}&genre=${encodeURIComponent(genre)}&rank=${encodeURIComponent(rank)}&tts_language=${encodeURIComponent(lang)}`;
    const r = await fetch(u, { headers }); if(!r.ok) throw new Error("Fetch failed: "+r.status);
    return await r.json();
  }
  function playOne(u){ return new Promise((resolve,reject)=>{ const a=new Audio(u); a.onended=resolve; a.onerror=()=>reject(new Error("Audio error: "+u)); a.play().catch(reject); }); }
  async function playSeq(urls){ for(const u of urls) await playOne(u); }
  async function startSpotify(){
    const p = `${base}/supabase/play-track-by-rank?decade=${encodeURIComponent(decade)}&genre=${encodeURIComponent(genre)}&rank=${encodeURIComponent(rank)}&play_intro=false&play_detail=false&play_artist_description=false&play_track=true&tts_language=${encodeURIComponent(lang)}`;
    const r = await fetch(p, { headers }); if(!r.ok) throw new Error("Spotify play failed: " + r.status);
  }
  document.getElementById('go').onclick = async ()=>{
    try{
      status("Fetching narration URLs…");
      const b = await bundle();
      const urls = []; if(Array.isArray(b.intros)) urls.push(...b.intros); if(b.detail) urls.push(b.detail); if(b.artist) urls.push(b.artist);
      if(urls.length){ status("Playing narration ("+urls.length+")…"); await playSeq(urls); } else { status("No narration; starting Spotify…"); }
      status("Starting Spotify on this device…");
      await startSpotify();
      status("Done. If you don't hear music, open Spotify once to activate this device, then tap Start again.");
    }catch(e){ console.error(e); status("Error: "+e.message); }
  };
})();
</script>
""")
