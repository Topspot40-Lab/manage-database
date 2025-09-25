# backend/routers/generate_folk_acoustic.py
from __future__ import annotations

import os
import math
import re
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Literal

import requests
import spotipy
from fastapi import APIRouter, HTTPException, Query
from spotipy.oauth2 import SpotifyClientCredentials

from backend.config import (
    # Spotify creds
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    # xAI
    XAI_API_KEY,
    XAI_API_URL,
    XAI_MODEL,
    TEMPERATURE_DEFAULT,
    # Supabase
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    # paths
    BASE_DIR,
)

logger = logging.getLogger("tts_logger")

folk_router = APIRouter(prefix="/generate/folk-acoustic")

# ─────────────────────────────────────────────────────────────────────────────
# Path helpers + JSON emitter
# ─────────────────────────────────────────────────────────────────────────────

def _slug(label: str) -> str:
    slug = label.lower().replace(" ", "_").replace("-", "_")
    slug = slug.strip("_")   # <-- remove leading/trailing underscores
    return slug

def _outdir_for_decade(decade_name: str) -> Path:
    d = BASE_DIR / "data" / "json_files" / "genredecade" / decade_name
    d.mkdir(parents=True, exist_ok=True)
    return d

def _build_decade_payload_en(
    *,
    decade_name: str,
    genre_label: str,             # e.g. "Folk Acoustic"
    tracks: List[Dict[str, Any]], # fields: ranking, spotify_*_id, names, album/year, detail/intro/artist_description, optionals
) -> Dict[str, Any]:
    genre_lower = genre_label.lower()

    # Top-level artist list (dedup by artist id)
    seen_art: Set[str] = set()
    artist_list: List[Dict[str, Any]] = []
    for t in tracks:
        aid = t["spotify_artist_id"]
        if aid in seen_art:
            continue
        seen_art.add(aid)
        artist_list.append({
            "artist_name": t["artist_name"],
            "spotify_artist_id": aid,
            "artist_artwork": t.get("artist_artwork"),
            "artist_description": t.get("artist_description", ""),
            "not_on_spotify": False,
        })

    # Track array (+detail) and track_ranking (+intro)
    track_items: List[Dict[str, Any]] = []
    track_ranking: List[Dict[str, Any]] = []

    for t in sorted(tracks, key=lambda x: int(x["ranking"])):
        artist_name = t["artist_name"]
        track_name  = t["track_name"]

        track_items.append({
            "rank": int(t["ranking"]),
            "track_name": track_name,
            "artist_name": artist_name.lower(),                 # mirrors your sample
            "artist_display_name": artist_name.title(),         # Title Case variant
            "featured_artist": t.get("featured_artist"),
            "featured_artist_id": t.get("featured_artist_id"),
            "track_display_name": track_name,
            "genre": genre_lower,
            "decade": decade_name,
            "spotify_track_id": t["spotify_track_id"],
            "spotify_artist_id": t["spotify_artist_id"],
            "mode_flag": "SOLO",
            "duration_ms": t.get("duration_ms"),
            "popularity": t.get("popularity"),
            "album_artwork": t.get("album_artwork"),
            "album_name": t.get("album_name"),
            "year_released": t.get("year"),
            "is_explicit": bool(t.get("is_explicit", False)),
            "created_at": datetime.utcnow().date().isoformat(),
            "detail": t.get("detail", ""),
        })

        track_ranking.append({
            "track_id": t["spotify_track_id"],
            "track_name": track_name,
            "artist_name": artist_name.lower(),
            "rank": int(t["ranking"]),
            "genre": genre_lower,
            "decade": decade_name,
            "tracklist": "TopSpot Autogen",
            "intro": t.get("intro", ""),
            "created_at": datetime.utcnow().date().isoformat(),
        })

    payload = {
        "language": "english",  # file remains *_en.json per your request
        "category": decade_name,
        "genre": genre_lower,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "genre_table": [{"genre_name": genre_label}],
        "decade": [{"decade_name": decade_name}],
        "artist": artist_list,
        "track": track_items,
        "tracklist": [{
            "name": "TopSpot Autogen",
            "curator": "TopSpot",
            "is_official": True,
            "language": "en",
            "notes": f"Generated for {genre_lower} - {decade_name}",
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        }],
        "track_ranking": track_ranking,
    }
    return payload

def _write_decade_file_en(decade_name: str, genre_label: str, tracks: List[Dict[str, Any]]) -> Path:
    genre_slug = _slug(genre_label)          # → "folk_acoustic"
    fname = f"{decade_name}_{genre_slug}_en.json"
    outdir = _outdir_for_decade(decade_name)
    out_path = outdir / fname
    data = _build_decade_payload_en(decade_name=decade_name, genre_label=genre_label, tracks=tracks)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path

# ─────────────────────────────────────────────────────────────────────────────
# Tunables / heuristics
# ─────────────────────────────────────────────────────────────────────────────
FOLK_GENRE_TERMS = {
    "folk", "acoustic", "bluegrass", "old-time", "old time", "americana", "appalachian",
    "celtic", "irish", "scottish", "british", "english", "australian", "bush ballad",
    "sea shanty", "shanty", "skiffle", "singer-songwriter", "neo-folk", "trad",
}

DECADES: List[Tuple[int, int, str]] = [
    (1950, 1959, "1950s"),
    (1960, 1969, "1960s"),
    (1970, 1979, "1970s"),
    (1980, 1989, "1980s"),
    (1990, 1999, "1990s"),
    (2000, 2009, "2000s"),
    (2010, 2019, "2010s"),
    (2020, 2029, "2020s"),
]

SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "US")

# ─────────────────────────────────────────────────────────────────────────────
# Spotify client
# ─────────────────────────────────────────────────────────────────────────────
def _get_spotify() -> spotipy.Spotify:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(
            status_code=400,
            detail="Missing Spotify credentials. Set SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET "
                   "or SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET in your .env"
        )
    auth = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
    return spotipy.Spotify(auth_manager=auth, requests_timeout=15, retries=3)

# ─────────────────────────────────────────────────────────────────────────────
# xAI helpers (kept simple)
# ─────────────────────────────────────────────────────────────────────────────
def _xai_chat(system: str, user: str, max_tokens=512) -> str:
    if not (XAI_API_KEY and XAI_API_URL and XAI_MODEL):
        logger.warning("xAI not configured — returning empty text")
        return ""
    headers = {"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": XAI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": TEMPERATURE_DEFAULT,
        "max_tokens": max_tokens,
        "stream": False,
    }
    r = requests.post(XAI_API_URL, headers=headers, json=payload, timeout=(10, 60))
    r.raise_for_status()
    data = r.json()
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()

def gen_intro(track_name: str, artist_name: str, decade_name: str, genre_label: str = "Folk Acoustic") -> str:
    system = "You are a radio host. Write a concise, hype but tasteful one-sentence intro for a track."
    user = (
        f"Introduce the song '{track_name}' by {artist_name} for a {genre_label} "
        f"set focused on the {decade_name}. Keep it 1 sentence, no markdown, "
        f"no added facts, 18–30 words, announcer tone."
    )
    return _xai_chat(system, user, max_tokens=120)

def gen_detail(track_name: str, artist_name: str, album: str, year: int) -> str:
    system = "You are a music curator. Write a compact 1–3 sentence detail for a track."
    user = (
        f"Song: {track_name}\nArtist: {artist_name}\nAlbum/session: {album}\nYear: {year}\n\n"
        "Constraints:\n- Keep facts verifiable and minimal.\n"
        "- Mention origin/style ONLY if widely known.\n"
        "- No markdown; 1–3 sentences; 40–65 words total."
    )
    return _xai_chat(system, user, max_tokens=220)

def gen_artist_bio(artist_name: str) -> str:
    system = "You are a music editor. Write a tight, evergreen artist blurb."
    user = (
        f"Artist: {artist_name}\n\nConstraints:\n- 1–2 sentences; 25–45 words.\n"
        "- Focus on era/scene and why they matter within folk/acoustic traditions.\n"
        "- No discography list; no markdown."
    )
    return _xai_chat(system, user, max_tokens=160)

# ─────────────────────────────────────────────────────────────────────────────
# Supabase helpers (fast, decade-scoped dedupe by default)
# ─────────────────────────────────────────────────────────────────────────────
def _get_supabase_client():
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        raise HTTPException(
            status_code=400,
            detail="Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in your .env"
        )
    try:
        from supabase import create_client
    except ImportError:
        raise HTTPException(
            status_code=400,
            detail="supabase-py not installed. Run: pip install supabase"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def _fetch_ids_page(q, start: int, end: int) -> List[Dict[str, Any]]:
    # Helper to trap per-page errors gracefully
    try:
        resp = q.range(start, end).execute()
        return resp.data or []
    except Exception as ex:
        logger.warning("Supabase fetch page %s-%s failed: %s", start, end, ex)
        return []

def get_existing_track_ids_supabase_global(
    table_name: str = "track",
    *,
    page_size: int = 1000,
    max_rows: int = 50000,
) -> Set[str]:
    sb = _get_supabase_client()
    ids: Set[str] = set()
    page = 0
    q = sb.table(table_name).select("spotify_track_id")
    logger.info("🔗 Supabase dedupe (global): page_size=%s max_rows=%s", page_size, max_rows)
    while True:
        rows = _fetch_ids_page(q, page * page_size, page * page_size + page_size - 1)
        for r in rows:
            sid = (r.get("spotify_track_id") or "").strip()
            if sid:
                ids.add(sid)
        if len(rows) < page_size or len(ids) >= max_rows:
            break
        page += 1
    logger.info("🔗 Supabase dedupe (global) loaded %d ids", len(ids))
    return ids

def get_existing_track_ids_supabase_decade(
    year_min: int,
    year_max: int,
    table_name: str = "track",
    *,
    page_size: int = 1000,
    max_rows: int = 20000,
) -> Set[str]:
    sb = _get_supabase_client()
    ids: Set[str] = set()
    page = 0

    # Try common column names for year
    year_cols = ["year_released", "yearReleased", "release_year"]

    # Build base query with filters; if filter fails (column missing), we fall back to global but capped
    q = None
    for col in year_cols:
        try:
            q = sb.table(table_name).select("spotify_track_id").gte(col, year_min).lte(col, year_max)
            # probe one page to verify column works
            _ = _fetch_ids_page(q, 0, 0)
            logger.info("🔗 Supabase dedupe (decade) using column %r %s–%s", col, year_min, year_max)
            break
        except Exception:
            q = None

    if q is None:
        logger.warning("⚠️ Supabase year filter unavailable; falling back to global capped fetch.")
        return get_existing_track_ids_supabase_global(table_name, page_size=page_size, max_rows=max_rows)

    while True:
        rows = _fetch_ids_page(q, page * page_size, page * page_size + page_size - 1)
        for r in rows:
            sid = (r.get("spotify_track_id") or "").strip()
            if sid:
                ids.add(sid)
        if len(rows) < page_size or len(ids) >= max_rows:
            break
        page += 1
    logger.info("🔗 Supabase dedupe (decade) loaded %d ids", len(ids))
    return ids

# ─────────────────────────────────────────────────────────────────────────────
# Spotify search strategy
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Pick:
    track_id: str
    track_name: str
    artist_id: str
    artist_name: str
    album: str
    year: int
    album_artwork: Optional[str] = None
    duration_ms: Optional[int] = None
    popularity: Optional[int] = None
    is_explicit: Optional[bool] = False

def _genre_ok(genres: List[str]) -> bool:
    gset = {g.lower() for g in genres}
    return any(term in " ".join(gset) for term in FOLK_GENRE_TERMS)

# Strongest-to-weakest artist search flavors
_ARTIST_QUERY_FLAVORS = [
    'genre:"folk"', 'genre:"bluegrass"', 'genre:"celtic"', 'genre:"americana"',
    'genre:"acoustic"', 'genre:"singer-songwriter"',
    # keyword fallbacks (still artist search)
    'folk', 'bluegrass', 'celtic', 'americana', 'acoustic', 'singer-songwriter',
]

# Track keyword flavors used only in fallback phase
_TRACK_QUERY_FLAVORS = [
    "folk", "bluegrass", "celtic", "americana", "acoustic",
    "sea shanty", "shanty", "skiffle", "old-time", "appalachian",
]

def _search_decade(
    sp: spotipy.Spotify,
    start: int,
    end: int,
    target: int,
    *,
    max_queries: int = 2,
    max_offsets: int = 2,
    page_limit: int = 25,
    market: str = SPOTIFY_MARKET,
    albums_per_artist: int = 2,
    tracks_per_album: int = 4,
) -> List[Pick]:
    """
    Phase A (primary): ARTIST search (genre works here), then sample tracks from decade albums/singles.
    Phase B (fallback): TRACK search by keyword + year range, then filter by artist genres.
    """
    picks: Dict[str, Pick] = {}
    year_min, year_max = start, end

    # -------- Phase A: artist-first --------
    tried_queries = 0
    for q in _ARTIST_QUERY_FLAVORS:
        if tried_queries >= max_queries:
            break

        for page_idx in range(max_offsets):
            offset = page_idx * page_limit
            try:
                res = sp.search(q=q, type="artist", limit=page_limit, offset=offset)
                artists = (res.get("artists") or {}).get("items") or []
                logger.debug("🎣 artist search q=%r off=%d → %d artists", q, offset, len(artists))
            except Exception as ex:
                logger.warning("Spotify artist search error for %r off=%d: %s", q, offset, ex)
                artists = []

            if not artists and page_idx == 0:
                break  # don't keep paging a dead query

            for a in artists:
                aid = a.get("id")
                aname = a.get("name") or "Unknown"
                if not aid:
                    continue

                ag = [g.lower() for g in (a.get("genres") or [])]
                if 'genre:' in q and not _genre_ok(ag):
                    continue

                try:
                    albums = sp.artist_albums(aid, album_type="album,single", country=market, limit=50)
                    album_items = albums.get("items") or []
                except Exception as ex:
                    logger.warning("artist_albums failed for %s: %s", aname, ex)
                    continue

                taken_albums = 0
                for alb in album_items:
                    if taken_albums >= albums_per_artist:
                        break
                    album_id = alb.get("id")
                    album_name = alb.get("name") or "Single"
                    rd = (alb.get("release_date") or "0000")[:4]
                    try:
                        ayear = int(rd)
                    except ValueError:
                        continue
                    if not (year_min <= ayear <= year_max):
                        continue

                    try:
                        tpage = sp.album_tracks(album_id, limit=50)
                        titems = tpage.get("items") or []
                    except Exception as ex:
                        logger.warning("album_tracks failed for %s (%s): %s", album_name, album_id, ex)
                        continue

                    taken_tracks = 0
                    for t in titems:
                        if taken_tracks >= tracks_per_album:
                            break
                        tid = t.get("id")
                        tname = t.get("name") or ""
                        if not tid or tid in picks:
                            continue

                        picks[tid] = Pick(
                            track_id=tid,
                            track_name=tname,
                            artist_id=aid,
                            artist_name=aname,
                            album=album_name,
                            year=ayear,
                        )
                        taken_tracks += 1

                        if len(picks) >= target:
                            logger.info("🎯 Phase A reached target with %d picks", len(picks))
                            return list(picks.values())

                    taken_albums += 1

        tried_queries += 1

    # -------- Phase B: track fallback --------
    logger.info("🔁 Phase A yielded %d picks; falling back to track search", len(picks))
    for q in _TRACK_QUERY_FLAVORS[:max_queries]:
        for page_idx in range(max_offsets):
            offset = page_idx * page_limit
            try:
                tq = f'{q} year:{year_min}-{year_max}'
                res = sp.search(q=tq, type="track", limit=page_limit, offset=offset)
                titems = (res.get("tracks") or {}).get("items") or []
                logger.debug("🎯 track search q=%r off=%d → %d tracks", tq, offset, len(titems))
            except Exception as ex:
                logger.warning("Spotify track search error for %r off=%d: %s", q, offset, ex)
                titems = []

            if not titems and page_idx == 0:
                break

            for t in titems:
                tid = t.get("id")
                tname = (t.get("name") or "").strip()
                album_name = ((t.get("album") or {}).get("name") or "Single").strip()
                rd = ((t.get("album") or {}).get("release_date") or "0000")[:4]
                try:
                    ayear = int(rd)
                except ValueError:
                    continue
                arts = t.get("artists") or []
                if not arts:
                    continue
                a0 = arts[0]
                aid = a0.get("id")
                aname = a0.get("name") or "Unknown"
                if not (tid and aid) or tid in picks:
                    continue

                # genre filter by primary artist
                try:
                    ainfo = sp.artist(aid)
                    ag = [g.lower() for g in (ainfo.get("genres") or [])]
                except Exception:
                    ag = []
                if not _genre_ok(ag):
                    continue

                picks[tid] = Pick(
                    track_id=tid,
                    track_name=tname,
                    artist_id=aid,
                    artist_name=aname,
                    album=album_name,
                    year=ayear,
                )

                if len(picks) >= target:
                    logger.info("🎯 Phase B reached target with %d picks", len(picks))
                    return list(picks.values())

    logger.info("ℹ️ Finished search with %d picks total", len(picks))
    return list(picks.values())

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint (Supabase-only dedupe; decade-scoped by default)
# ─────────────────────────────────────────────────────────────────────────────
@folk_router.post("/build")
def build_folk_acoustic_catalog(
    per_decade: int = Query(45, ge=10, le=100),
    max_overlap_pct: float = Query(5.0, ge=0.0, le=20.0),
    write_files: bool = Query(True, description="Write JSON files under data/json_files/decadegenre/<decade>"),
    generate_copy: bool = Query(True, description="Call xAI to fill intro/detail/artist_description"),
    decades: Optional[str] = Query(None, description="Comma-separated, e.g. 1960s,1970s (default: all)"),
    language: str = Query("en"),
    max_queries: int = Query(2, ge=1, le=10),
    max_offsets: int = Query(2, ge=1, le=10),
    page_limit: int = Query(25, ge=5, le=50),
    allow_partial: bool = Query(True),
    market: Optional[str] = Query(None, description="Spotify market like US, GB, IE"),
    dedupe_table: str = Query("track", description="Supabase table name to dedupe against"),
    dedupe_scope: Literal["decade", "global", "none"] = Query("decade"),
    dedupe_max_rows: int = Query(20000, ge=1000, le=200000, description="Safety cap for Supabase dedupe fetch"),
    dry_run: bool = Query(False),
    max_copy_per_decade: int = Query(0, ge=0, le=45, description="Cap xAI calls per decade (0 = no cap)"),
):
    """
    Build 'Folk Acoustic' sets across decades.
    Dedupes strictly against Supabase (no local DB).
    - dedupe_scope=decade (default): only fetch IDs for that decade's year range → fastest
    - dedupe_scope=global: fetch IDs for the whole table (capped by dedupe_max_rows)
    - dedupe_scope=none: skip dedupe (for quick smoke tests)

    Quick test:
      /generate/folk-acoustic/build?decades=1960s&per_decade=10&generate_copy=false&write_files=false&allow_partial=true&max_queries=2&max_offsets=2&page_limit=25&dedupe_scope=decade
    """
    lang = "pt-BR" if language.lower() in ("ptbr", "pt-br") else language

    wanted: Optional[Set[str]] = None
    if decades:
        wanted = {d.strip() for d in decades.split(",") if d.strip()}
    selected_decades = [(s, e, name) for (s, e, name) in DECADES if not wanted or name in wanted]
    if not selected_decades:
        return {"message": "No matching decades", "requested_decades": decades, "selected_decades": []}

    logger.info("🎯 Folk Acoustic build | per_decade=%s | lang=%s | copy=%s | decades=%s",
                per_decade, lang, generate_copy, [d for *_, d in selected_decades])
    logger.info("📉 Limits | overlap=%.2f%% | write_files=%s | throttle q=%s off=%s pg=%s | partial=%s | copy_cap=%s | dedupe_scope=%s max_rows=%s",
                max_overlap_pct, write_files, max_queries, max_offsets, page_limit, allow_partial, max_copy_per_decade,
                dedupe_scope, dedupe_max_rows)

    if dry_run:
        return {
            "message": "Dry run OK",
            "language": lang,
            "per_decade": per_decade,
            "selected_decades": [d for *_s, d in selected_decades],
            "actions": [
                f"search Spotify: {max_queries} queries × {max_offsets} pages × {page_limit} items",
                f"dedupe: {dedupe_scope} (cap={dedupe_max_rows})",
                "generate copy" if generate_copy else "skip copy",
                "write files" if write_files else "skip write",
                "allow_partial" if allow_partial else "fill strictly",
            ],
        }

    # Spotify
    sp = _get_spotify()

    # Prepare global dedupe set if requested
    existing_ids_global: Set[str] = set()
    if dedupe_scope == "global":
        existing_ids_global = get_existing_track_ids_supabase_global(
            dedupe_table, page_size=1000, max_rows=dedupe_max_rows
        )

    decade_summaries = []
    written_files: List[str] = []

    for start, end, dname in selected_decades:
        logger.info("——— 🗓️  %s — start ———", dname)

        # Decide dedupe set for this decade
        if dedupe_scope == "none":
            existing_ids = set()
            logger.info("🧪 Dedupe OFF for %s", dname)
        elif dedupe_scope == "global":
            existing_ids = existing_ids_global
            logger.info("🧩 Dedupe (global) size=%d", len(existing_ids))
        else:
            # decade-scoped
            existing_ids = get_existing_track_ids_supabase_decade(
                start, end, dedupe_table, page_size=1000, max_rows=dedupe_max_rows
            )

        # Search (throttled)
        logger.info("🔎 Spotify search [%s]: q=%s off=%s pg=%s", dname, max_queries, max_offsets, page_limit)
        pool = _search_decade(
            sp, start, end, target=per_decade,
            max_queries=max_queries,
            max_offsets=max_offsets,
            page_limit=page_limit,
            market=(market or os.getenv("SPOTIFY_MARKET", "US")),
            albums_per_artist=2,
            tracks_per_album=4,
        )
        logger.info("✅ Pool ready [%s]: %d candidates", dname, len(pool))

        # Filter overlap with Supabase
        fresh = [p for p in pool if p.track_id not in existing_ids]
        logger.info("🧹 Fresh tracks [%s]: %d (existing filtered: %d)", dname, len(fresh), len(pool) - len(fresh))

        # Choose up to per_decade with small allowed dupes (from Supabase) if needed
        max_dupes = math.floor(per_decade * (max_overlap_pct / 100.0))
        chosen: List[Pick] = []
        chosen.extend(fresh[:per_decade])
        need = per_decade - len(chosen)

        if need > 0 and max_dupes > 0:
            dupes = [p for p in pool if p.track_id in existing_ids][:min(need, max_dupes)]
            chosen.extend(dupes)

        # Optionally widen search (skip if allow_partial)
        if not allow_partial and len(chosen) < per_decade:
            logger.info("➕ Widening search [%s] to fill remaining %d…", dname, per_decade - len(chosen))
            extra = _search_decade(
                sp, start, end, target=per_decade,
                max_queries=max_queries, max_offsets=max_offsets, page_limit=page_limit,
                market=(market or os.getenv("SPOTIFY_MARKET", "US")),
            )
            extra = [p for p in extra if p.track_id not in {c.track_id for c in chosen}]
            extra_fresh = [p for p in extra if p.track_id not in existing_ids]
            chosen.extend(extra_fresh[: (per_decade - len(chosen))])

        chosen = chosen[:per_decade]
        logger.info("📦 Selected [%s]: %d tracks (target=%d)", dname, len(chosen), per_decade)

        # Assemble payloads
        payloads: List[Dict[str, Any]] = []
        generated_this_decade = 0

        for idx, pick in enumerate(chosen, start=1):
            item: Dict[str, Any] = {
                "decade": dname,
                "genre": "Folk Acoustic",
                "ranking": idx,
                "spotify_track_id": pick.track_id,
                "track_name": pick.track_name,
                "spotify_artist_id": pick.artist_id,
                "artist_name": pick.artist_name,
                "album_name": pick.album,
                "year": pick.year,
                "album_artwork": None,
                "duration_ms": None,
                "popularity": None,
                "is_explicit": False,
                "intro": "",
                "detail": "",
                "artist_description": "",
            }

            if generate_copy and (max_copy_per_decade == 0 or generated_this_decade < max_copy_per_decade):
                try:
                    item["intro"] = gen_intro(pick.track_name, pick.artist_name, dname)
                except Exception as e:
                    logger.warning("💬 intro failed [%s #%d %s] — %s", dname, idx, pick.track_name, e)

                try:
                    item["detail"] = gen_detail(pick.track_name, pick.artist_name, pick.album, pick.year)
                except Exception as e:
                    logger.warning("💬 detail failed [%s #%d %s] — %s", dname, idx, pick.track_name, e)

                try:
                    item["artist_description"] = gen_artist_bio(pick.artist_name)
                except Exception as e:
                    logger.warning("💬 artist bio failed [%s #%d %s] — %s", dname, idx, pick.artist_name, e)

                generated_this_decade += 1

            payloads.append(item)

        logger.info("📝 Text generated [%s]: %d / %d tracks (cap=%d)",
                    dname, generated_this_decade, len(payloads), max_copy_per_decade)

        # Write file
        written_path = None
        if write_files:
            written_path = _write_decade_file_en(
                decade_name=dname,
                genre_label="Folk Acoustic",
                tracks=payloads
            )
            logger.info("💾 Wrote file [%s] → %s", dname, written_path)

        decade_summaries.append({
            "decade": dname,
            "requested": per_decade,
            "selected": len(payloads),
            "overlap_allowed_max": math.floor(per_decade * (max_overlap_pct / 100.0)),
            "pool_size": len(pool),
            "written": write_files,
            "file": str(written_path) if written_path else None,
        })

        logger.info("——— ✅ %s — done ———", dname)

    return {
        "message": "Folk Acoustic build complete",
        "per_decade": per_decade,
        "max_overlap_pct": max_overlap_pct,
        "language": lang,
        "decades": decade_summaries,
    }
