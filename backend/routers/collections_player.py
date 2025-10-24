from __future__ import annotations

import json
from typing import Literal
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import Session, select
import logging
from backend.database import get_db
from backend.utils.naming import normalize_language_code_canon
from backend.models.collection_models import Collection, CollectionTrackRanking
from backend.models.dbmodels import Track, Artist
from backend.services.narration_texts import assemble_narration_texts

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

logger = logging.getLogger(__name__)  # <-- define it once per module
router = APIRouter(prefix="/supabase/collections", tags=["Collections"])


# optional helper for consistent casing
def _titleize(s: str | None) -> str:
    return s.replace("_", " ").title() if s else ""

def collection_intro_jobs(*, lang: str, slug: str, rank: int):
    """
    Build server-side intro job list for collections:
    uses bucket audio-<lang>, key collections-intro/{slug}_{rank:02d}.mp3
    Tuple shape matches what play_narrations expects.
    """
    bucket = bucket_for(lang, "intro")  # e.g., audio-en, audio-es, audio-ptbr
    key = f"collections-intro/{slug}_{rank:02d}.mp3"
    return [(bucket, key, "collection", slug, rank)]

# ─────────────────────────────────────────────────────────────
# PLAY SINGLE TRACK BY RANK (server-side playback)
# ─────────────────────────────────────────────────────────────
@router.get("/play-track-by-rank")
async def play_track_by_rank(
    collection_slug: str = Query(...),
    rank: int = Query(...),
    play_intro: bool | str = Query(True),
    play_detail: bool | str = Query(True),
    play_track: bool | str = Query(True),
    play_artist_description: bool | str = Query(True),
    tts_language: Literal["en","es","ptbr","pt-BR"] = Query("en"),
    db: Session = Depends(get_db),
):
    # ─────────────────────────────────────────────
    # Normalize boolean query params
    # ─────────────────────────────────────────────
    def str_to_bool(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        return str(val).strip().lower() in {"true", "1", "yes", "y", "t"}

    play_intro = str_to_bool(play_intro)
    play_detail = str_to_bool(play_detail)
    play_artist_description = str_to_bool(play_artist_description)
    play_track = str_to_bool(play_track)

    logger.info(
        f"🎛️ Flags received → intro={play_intro}, detail={play_detail}, "
        f"artist={play_artist_description}, track={play_track}"
    )

    # ─────────────────────────────────────────────
    # Resolve collection and track data
    # ─────────────────────────────────────────────
    lang = normalize_language_code_canon(tts_language)
    coll = db.exec(select(Collection).where(Collection.slug == collection_slug)).first()
    if not coll:
        return {"error": f"No Collection for {collection_slug!r}"}

    ctr_row = db.exec(
        select(
            CollectionTrackRanking.id,
            CollectionTrackRanking.ranking,
            CollectionTrackRanking.track_id,
            CollectionTrackRanking.intro,
        ).where(
            CollectionTrackRanking.collection_id == coll.id,
            CollectionTrackRanking.ranking == rank
        )
    ).first()

    if not ctr_row:
        return {"error": f"No ranking #{rank} in collection {collection_slug}"}

    ctr = getattr(ctr_row, "_mapping", ctr_row)
    track = db.get(Track, ctr["track_id"])
    artist = db.get(Artist, track.artist_id) if track else None
    if not track or not artist:
        return {"error": "Track or Artist not found"}

    # ─────────────────────────────────────────────
    # Pull texts from correct sources
    # ─────────────────────────────────────────────
    intro_text = ctr.get("intro")
    detail_text = (
        getattr(track, "detail_text", None)
        or getattr(track, "track_detail", None)
        or getattr(track, "detail", None)
    )

    log_collection_header_and_texts(
        lang=lang,
        collection=coll,
        ctr=ctr,
        track=track,
        artist=artist,
        intro=intro_text,
        detail_text=detail_text,
    )

    # ─────────────────────────────────────────────
    # Narration playback setup
    # ─────────────────────────────────────────────
    detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
        lang=lang, track=track, artist=artist
    )

    intro_jobs = (
        collection_intro_jobs(lang=lang, slug=coll.slug, rank=rank)
        if play_intro
        else []
    )

    # Play narrations only for selected flags
    if intro_jobs or (play_detail and detail_bucket and detail_key) or (
        play_artist_description and artist_bucket and artist_key
    ):
        await maybe_play_bed()

    await play_narrations(
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist=play_artist_description,
        intro_jobs=intro_jobs,
        detail_bucket=detail_bucket,
        detail_key=detail_key,
        artist_bucket=artist_bucket,
        artist_key=artist_key,
    )

    # ─────────────────────────────────────────────
    # Spotify playback
    # ─────────────────────────────────────────────
    if play_track and track.spotify_track_id:
        skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
        if skipped_mid:
            return {
                "status": "skipped",
                "collection": collection_slug,
                "rank": rank,
            }

    collection_intro = None
    if hasattr(ctr, "get"):
        collection_intro = ctr.get("intro")
    else:
        collection_intro = getattr(ctr, "intro", None)

    texts = assemble_narration_texts(
        track=track,
        artist=artist,
        collection_intro=collection_intro,
        mode="collection"
    )

    return {
        "status": "success",
        "collection": collection_slug,
        "rank": rank,
        **texts
    }


# ─────────────────────────────────────────────────────────────
# PLAY COLLECTION SEQUENCE (count up / down / random)
# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
# PLAY COLLECTION SEQUENCE (supports start/end rank + "All")
# ─────────────────────────────────────────────────────────────

@router.get("/play-sequence", response_class=HTMLResponse)
async def play_sequence(
    request: Request,
    collection_slug: str = Query(..., description="'All' plays all collections combined"),
    start_rank: int = Query(1, ge=1, le=40),
    end_rank: int = Query(40, ge=1, le=40),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_track: bool = Query(True),
    play_artist_description: bool = Query(True),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    ui: int = Query(1, description="1=HTML player (browser). 0=JSON bundle."),
    server: bool = Query(True, description="True=server-side playback like Car Mode."),
    expires: int = Query(300, ge=60, le=3600),
    db: Session = Depends(get_db),
):
    lang = normalize_language_code_canon(tts_language)

    # Handle "All" collections
    if collection_slug.lower() == "all":
        collections = db.exec(select(Collection)).all()
        if not collections:
            return JSONResponse({"error": "No collections found."}, status_code=404)
    else:
        coll = db.exec(select(Collection).where(Collection.slug == collection_slug)).first()
        if not coll:
            return JSONResponse({"error": f"No Collection for {collection_slug!r}"}, status_code=404)
        collections = [coll]

    # Gather all ranking rows
    rows = []
    for c in collections:
        rows.extend(
            db.exec(
                select(CollectionTrackRanking)
                .where(CollectionTrackRanking.collection_id == c.id)
                .order_by(CollectionTrackRanking.ranking)
            ).all()
        )

    if not rows:
        return JSONResponse({"error": "No rankings found for selection."}, status_code=404)

    # Filter by rank range
    rows = [r for r in rows if start_rank <= r.ranking <= end_rank]
    if not rows:
        return JSONResponse({"error": f"No tracks in rank range {start_rank}-{end_rank}."}, status_code=404)

    # Determine play order
    order = sorted({r.ranking for r in rows})
    if mode == "count_up":
        play_order = sorted(order)
    elif mode == "count_down":
        play_order = sorted(order, reverse=True)
    else:
        import random
        play_order = list(order)
        random.shuffle(play_order)

    # ─────────────────────────────────────────────────────────────
    # SERVER MODE: playback handled on backend (Car Mode)
    # ─────────────────────────────────────────────────────────────
    if server:
        results = []
        for rk in play_order:
            matching_rows = [r for r in rows if r.ranking == rk]
            for r in matching_rows:
                track = db.get(Track, r.track_id)
                artist = db.get(Artist, track.artist_id) if track else None
                if not track or not artist:
                    continue

                # ✅ Use intro from CollectionTrackRanking
                intro_text = getattr(r, "intro", None)
                detail_text = (
                    getattr(track, "detail_text", None)
                    or getattr(track, "track_detail", None)
                    or getattr(track, "detail", None)
                )

                # ✅ Display header and intro
                coll_for_row = next((c for c in collections if c.id == r.collection_id), None)
                log_collection_header_and_texts(
                    lang=lang,
                    collection=coll_for_row,
                    ctr=r,
                    track=track,
                    artist=artist,
                    intro=intro_text,
                    detail_text=detail_text,
                )

                # Narrations (optional playback order, but no autoplay)
                detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
                    lang=lang, track=track, artist=artist
                )
                intro_jobs = collection_intro_jobs(lang=lang, slug=coll_for_row.slug, rank=rk) if play_intro else []

                # Queue narrations if available (no autoplay)
                await maybe_play_bed()
                await play_narrations(
                    play_intro=False,  # ❌ no autoplay
                    play_detail=False,
                    play_artist=False,
                    intro_jobs=intro_jobs,
                    detail_bucket=detail_bucket, detail_key=detail_key,
                    artist_bucket=artist_bucket, artist_key=artist_key,
                )

                results.append({
                    "rank": rk,
                    "track": track.track_name,
                    "artist": artist.artist_name if artist else None,
                    "album_name": getattr(track, "album_name", None),
                    "album_artwork": getattr(track, "album_artwork", None),
                    "collection": coll_for_row.slug if coll_for_row else None,
                })

        # ─────────────────────────────────────────────────────────────
        # Return HTML page (for UI popup) or JSON (for API)
        # ─────────────────────────────────────────────────────────────
        if ui == 1:
            # Sort results by rank for consistent display
            detailed_results = []
            for r in sorted(results, key=lambda r: r["rank"]):
                track = db.exec(select(Track).where(Track.track_name == r["track"])).first()
                artist = db.exec(select(Artist).where(Artist.id == track.artist_id)).first() if track else None
                detailed_results.append({
                    "rank": r["rank"],
                    "track": _titleize(getattr(track, "track_name", None) or r["track"]),
                    "artist": _titleize(getattr(artist, "artist_name", None) or "Unknown Artist"),
                    "year_released": getattr(track, "year_released", None),
                    "collection": _titleize(r["collection"]),
                })

            html = f"""
            <html>
              <head>
                <title>TopSpot — {collections[0].name if collections else 'Collection'}</title>
                <style>
                  body {{
                    font-family: 'Segoe UI', sans-serif;
                    background: #121212;
                    color: #e0e0e0;
                    padding: 1.5rem;
                    line-height: 1.5;
                  }}
                  h2 {{
                    color: #24c661;
                    margin-bottom: 1rem;
                  }}
                  table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 1rem;
                  }}
                  th, td {{
                    border-bottom: 1px solid #333;
                    padding: 0.5rem 0.75rem;
                    text-align: left;
                  }}
                  th {{
                    background-color: #1e1e1e;
                    color: #76e2ff;
                  }}
                  tr:hover td {{
                    background-color: #222;
                  }}
                  td.rank {{
                    color: #24c661;
                    font-weight: bold;
                  }}
                  td.year {{
                    color: #aaa;
                  }}
                </style>
              </head>
              <body>
                <h2>🎧 TopSpot Player — {collections[0].name if collections else ''}</h2>
                <p><b>Mode:</b> {mode.replace('_',' ').title()} &nbsp; | &nbsp;
                   <b>Range:</b> {start_rank}-{end_rank} &nbsp; | &nbsp;
                   <b>Language:</b> {lang.upper()}</p>
                <table>
                  <thead>
                    <tr>
                      <th>#</th><th>Track</th><th>Artist</th><th>Year</th><th>Collection</th>
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(f"<tr><td class='rank'>{r['rank']}</td><td>{r['track']}</td><td>{r['artist']}</td><td class='year'>{r['year_released'] or ''}</td><td>{r['collection']}</td></tr>" for r in detailed_results)}
                  </tbody>
                </table>
              </body>
            </html>
            """
            return HTMLResponse(content=html)

        # Default JSON response (for backend or Car Mode)
        # ✅ Include album fields for Car Mode and frontend
        return JSONResponse({
            "status": "loaded",
            "collections": [c.slug for c in collections],
            "mode": mode,
            "range": [start_rank, end_rank],
            "language": lang,
            "tracks_loaded": [
                {
                    "rank": r["rank"],
                    "track": r["track"],
                    "artist": r["artist"],
                    "album_name": r.get("album_name"),
                    "album_artwork": r.get("album_artwork"),
                    "collection": r["collection"],
                }
                for r in results
            ],
        })

    # ─────────────────────────────────────────────────────────────
    # BROWSER MODE: return signed URL bundle (no autoplay)
    # ─────────────────────────────────────────────────────────────
    sequence = []
    for r in rows:
        coll_for_row = next((c for c in collections if c.id == r.collection_id), None)
        if not coll_for_row:
            continue

        # ✅ fetch track & artist so we can include album fields
        t = db.get(Track, r.track_id)
        a = db.get(Artist, t.artist_id) if t else None
        if not t:
            continue

        bundle, err = urls_for_rank_collection(
            db=db,
            lang=lang,
            collection_id=coll_for_row.id,
            rank=r.ranking,
            use_intro=play_intro,
            use_detail=play_detail,
            use_artist=play_artist_description,
            expires=expires,
            request=request,
            collection_slug=coll_for_row.slug,
        )
        if err or not bundle:
            continue

        sequence.append({
            "rank": r.ranking,
            "collection": coll_for_row.slug,
            # ✅ include names + album info
            "track_name": getattr(t, "track_name", None),
            "artist_name": getattr(a, "artist_name", None) if a else None,
            "album_name": getattr(t, "album_name", None),
            "album_artwork": getattr(t, "album_artwork", None),
            **bundle,
        })

    # Keep DB rank, not bundle rank
    for s in sequence:
        # ensure rank is from CollectionTrackRanking, not bundle
        s["rank"] = int(s.get("rank", 0))

    # Sort to match mode
    if mode == "count_up":
        sequence.sort(key=lambda s: s["rank"])
    elif mode == "count_down":
        sequence.sort(key=lambda s: s["rank"], reverse=True)
    else:  # random
        import random
        random.shuffle(sequence)

    base = str(request.base_url).rstrip("/")
    if ui == 0:
        return JSONResponse({
            "collections": [c.slug for c in collections],
            "mode": mode,
            "language": lang,
            "range": [start_rank, end_rank],
            "play_track": play_track,
            "expires": expires,
            "sequence": sequence
        })

    html = f"""<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>TopSpot Collections — Range {start_rank}-{end_rank}</title>
<style>
 body{{font:16px/1.5 system-ui,Segoe UI,Roboto,Arial;background:#0b0b0c;color:#e6e6e6;max-width:760px;margin:24px auto;padding:0 14px}}
 button{{font:inherit;padding:10px 14px;border-radius:12px;border:0;background:#2b6;cursor:pointer}}
 .muted{{color:#9aa}} .row{{margin:.5rem 0}}
 .badge{{display:inline-block;background:#222;border:1px solid #333;border-radius:10px;padding:2px 8px;margin-right:6px}}
 ol{{margin-top:12px}} .log{{white-space:pre-wrap;background:#111;border:1px solid #222;border-radius:12px;padding:10px;margin-top:12px;max-height:40vh;overflow:auto}}
</style>
<h2>TopSpot — Collections Range {start_rank}-{end_rank}</h2>
<p class="muted">Mode: <b>{mode}</b> • Language: <b>{lang}</b></p>
<p class="muted">Collections: {', '.join(c.slug for c in collections)}</p>
<div class="row"><button id="loadBtn">📦 Load Tracks</button> <span id="status" class="badge">idle</span></div>
<ol id="list"></ol>
<div class="log" id="log"></div>

<script>
const seq = {json.dumps(sequence)};
const collections = {json.dumps([c.slug for c in collections])};

const elList = document.getElementById('list');
const elStatus = document.getElementById('status');
const elLog = document.getElementById('log');
function log(msg){{ elLog.textContent += msg + "\\n"; elLog.scrollTop = elLog.scrollHeight; }}
function setStatus(s){{ elStatus.textContent = s; }}

seq.forEach(step => {{
  const li = document.createElement('li');
  li.textContent = `#${{step.rank}} — ${{step.track_name}} — ${{step.artist_name||""}} [${{step.collection}}]`;
  elList.appendChild(li);
}});

document.getElementById('loadBtn').onclick = () => {{
  setStatus("loaded");
  log(`Loaded ${{seq.length}} tracks across ${{collections.length || 1}} collections`);

}};

</script>

"""
    return HTMLResponse(html)
