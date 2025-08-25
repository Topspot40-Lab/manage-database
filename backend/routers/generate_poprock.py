# backend/routers/generate_poprock.py
from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Tuple
import json, re, time, os, logging
from uuid import uuid4
from pathlib import Path as FsPath
from types import SimpleNamespace as _NS
from datetime import datetime

from backend.services.prompt_poprock import build_poprock_prompt
from backend.services.llm_client import complete_json  # def complete_json(prompt:str) -> dict

# === imports to mirror generate_json pipeline ===
from backend.utils.naming import slug_underscore, normalize_language_code
from backend.services.spotify.missing_log import handle_missing_track, reassign_ranks
from backend.builders.track_builder import build_track_entry
from backend.builders.json_builder import build_final_json
from backend.services.track_generator import enrich_tracks_with_spotify
from backend.services.xai_descriptions import get_track_descriptions_from_xai
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai
from backend.utils.json_helpers import save_full_json_file
from shared.filepaths import get_json_path
from backend.utils.log_helpers import log_generate_json_summary

router = APIRouter(prefix="", tags=["generate-json"])
logger = logging.getLogger(__name__)

# ── Fixed knobs per your request ─────────────────────────────────────────────
BUFFER_SIZE_FIXED = 0
MAX_TRACKS_PER_ARTIST_FIXED = 7
OVERLAP_ALLOWANCE_FIXED = 0
# Output path/format are now exactly the same as generate_json via get_json_path + save_full_json_file

# ---- Normalization helpers (ported from generate_json) ----
_CONNECTORS = [
    (r"\s+feat\.\s+", "FEATURED"),
    (r"\s+ft\.\s+", "FEATURED"),
    (r"\s+featuring\s+", "FEATURED"),
    (r"\s+with\s+", "DUET"),
    (r"\s+con\s+", "DUET"),       # es
    (r"\s+y\s+", "DUET"),         # es
    (r"\s+&\s+", "DUET"),
]

def _normalize_artist_collab(t: dict) -> dict:
    name = (t.get("artist_name") or "").strip()
    if not name:
        return t
    for pattern, mode in _CONNECTORS:
        parts = re.split(pattern, name, flags=re.IGNORECASE)
        if len(parts) >= 2:
            main = parts[0].strip()
            rest = " & ".join(p.strip() for p in parts[1:] if p.strip())
            t["artist_name"] = main
            if not (t.get("mode_flag") or "").strip():
                t["mode_flag"] = mode
            t["featured_artist"] = rest
            return t
    return t

def _to_snake_track(d: dict) -> dict:
    out = {}
    out["track_name"] = d.get("track_name") or d.get("trackName") or d.get("traackName") or d.get("title")
    out["artist_name"] = d.get("artist_name") or d.get("artistName") or d.get("artist")
    out["year_released"] = d.get("year_released") or d.get("yearReleased") or d.get("release_year")
    out["album_name"] = d.get("album_name") or d.get("albumName")
    out["rank"] = d.get("rank")
    out["mode_flag"] = d.get("mode_flag") or d.get("modeFlag") or ""
    out["mode_flag_detail"] = d.get("mode_flag_detail") or d.get("modeFlagDetail") or ""
    for k, v in d.items():
        if k not in out:
            out[k] = v
    return out

# ---- keys & overlap control for the initial POP/ROCK candidate lists ----
def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = re.sub(r"\s+", " ", s)
    return s

def _key(row: Dict[str, Any]) -> Tuple[str, str]:
    return _norm(row.get("artistName")), _norm(row.get("trackName"))

def _dedupe_keep_best(rows: List[Dict[str, Any]], score_fields: List[str]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str,str], Dict[str, Any]] = {}
    for r in rows:
        k = _key(r)
        prev = best.get(k)
        if not prev:
            best[k] = r
            continue
        prev_tuple = tuple(prev.get(sf, 0) for sf in score_fields)
        curr_tuple = tuple(r.get(sf, 0) for sf in score_fields)
        if curr_tuple > prev_tuple:
            best[k] = r
    return list(best.values())

def _trim_to_n(rows: List[Dict[str, Any]], n: int, score_fields: List[str]) -> List[Dict[str, Any]]:
    rows_sorted = sorted(rows, key=lambda r: tuple(r.get(sf, 0) for sf in score_fields), reverse=True)
    return rows_sorted[:n]

def _enforce_overlap(pop_rows: List[Dict[str, Any]], rock_rows: List[Dict[str, Any]], allowance: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[str,str]]]:
    pop_keys = {_key(r) for r in pop_rows}
    rock_keys = {_key(r) for r in rock_rows}
    overlap = list(pop_keys & rock_keys)

    if len(overlap) <= allowance:
        return pop_rows, rock_rows, overlap

    overlap_rows_rock = [r for r in rock_rows if _key(r) in overlap]
    overlap_rows_rock_sorted = sorted(overlap_rows_rock, key=lambda r: (r.get("importanceScore",0), r.get("rockScore",0)))
    to_remove = len(overlap) - allowance
    remove_set = {_key(r) for r in overlap_rows_rock_sorted[:to_remove]}
    rock_rows = [r for r in rock_rows if _key(r) not in remove_set]

    final_overlap = list({_key(r) for r in pop_rows} & {_key(r) for r in rock_rows})
    return pop_rows, rock_rows, final_overlap

class GenerateOut(BaseModel):
    decade: str
    counts_before: Dict[str, int]
    overlap_after: int
    counts_final: Dict[str, int]
    saved_files: Dict[str, str]

# === internal: run the full generate_json pipeline for a single genre ===
def _process_genre(
    *,
    decade: str,
    genre: str,
    language: str,
    target_count: int,
    candidate_rows: List[Dict[str, Any]],
    request_id: str,
) -> Tuple[str, int]:
    """
    Returns: (final_path_str, final_track_count)
    """
    logger.debug("req=%s [%s] STEP A0: normalize rows to snake_case", request_id, genre)
    tracks = [_to_snake_track(t) for t in candidate_rows]
    tracks = [_normalize_artist_collab(t) for t in tracks]

    # === STEP 3 (generate_json): Spotify enrichment + filter missing ids ===
    logger.debug("req=%s [%s] STEP 3: enrich with Spotify", request_id, genre)
    enriched = {"tracks": tracks}
    enriched["tracks"] = enrich_tracks_with_spotify(enriched["tracks"], is_test_mode=False)
    before = len(enriched["tracks"])
    enriched["tracks"] = [t for t in enriched["tracks"] if t.get("spotify_track_id")]
    enriched["tracks"] = [_to_snake_track(t) for t in enriched["tracks"]]
    logger.info("req=%s [%s] STEP 3: filtered %d missing-spotify tracks", request_id, genre, before - len(enriched["tracks"]))

    # === STEP 4: build_final_json (same builder used in generate_json) ===
    now_dt = datetime.now()
    now_iso = now_dt.isoformat()
    req_obj = _NS(decade=decade, genre=genre, language=language, num_tracks=target_count)
    final_json, track_entries, artist_entries = build_final_json(
        enriched_tracks=enriched["tracks"],
        request=req_obj,
        now=now_iso,
        is_test_mode=False
    )

    # === STEP 5–8: handle missing IDs, remove, fill spares, reassign ranks ===
    tracks_tbl = final_json["track"]
    spares = final_json.get("spares", [])

    for track in tracks_tbl[:]:
        if not track.get("spotify_track_id"):
            handle_missing_track(track, tracks_tbl)

    tracks_tbl = [t for t in tracks_tbl if t.get("spotify_track_id")]

    while len(tracks_tbl) < target_count and spares:
        spare = spares.pop(0)
        spare = _to_snake_track(spare)
        missing_keys = [k for k in ("track_name","artist_name") if k not in spare or not spare.get(k)]
        if missing_keys:
            logger.warning("req=%s [%s] skipping spare missing %s: %s", request_id, genre, missing_keys, spare)
            continue
        try:
            rebuilt = build_track_entry(spare, req_obj, spotify_data=None, now=now_iso, is_test_mode=False)
            rebuilt["rank"] = len(tracks_tbl) + 1
            tracks_tbl.append(rebuilt)
        except Exception as e:
            logger.warning("req=%s [%s] spare rebuild failed: %s", request_id, genre, e)

    reassign_ranks(tracks_tbl)
    final_json["track"] = tracks_tbl

    # === STEP 9: add track descriptions; 9.B: artist descriptions ===
    enriched_for_xai = {
        "tracks": tracks_tbl,
        "track_ranking": final_json.get("track_ranking", []),
        "artist_table": final_json.get("artist_table", [])
    }

    described = get_track_descriptions_from_xai(
        track_data=enriched_for_xai,
        language=language,
        decade=decade,
        genre=genre
    )

    if not described or "tracks" not in described or len(described["tracks"]) != len(tracks_tbl):
        raise HTTPException(status_code=500, detail=f"Failed to generate final {genre} track descriptions")

    final_json["track"] = described["tracks"]
    final_json.update({"track_ranking": described.get("track_ranking", [])})
    final_json["artist_table"] = described.get("artist_table", [])

    core_artists = final_json.get("artist", [])
    if core_artists:
        artist_described = get_artist_descriptions_from_xai(core_artists, language)
        desc_map = {a["artist_name"].strip().lower(): a["artist_description"]
                    for a in artist_described if a.get("artist_description")}
        for artist in core_artists:
            name = (artist.get("artist_name") or "").strip().lower()
            if name in desc_map:
                artist["artist_description"] = desc_map[name]

    # === STEP 10: save in the exact same way as generate_json ===
    for t in (final_json.get("track") or []):
        mf = t.get("mode_flag")
        if mf is not None:
            t["mode_flag"] = str(mf).upper().strip()

    lang_code = normalize_language_code(language)
    filepath = get_json_path(decade, genre, lang_code)

    decade_slug = slug_underscore(decade)
    genre_slug  = slug_underscore(genre)

    # same filename rule as generate_json (no test flag here)
    filename = f"{decade_slug}_{genre_slug}_{lang_code}.json"

    base_dir = FsPath(filepath)
    if base_dir.suffix:
        base_dir = base_dir.parent
    final_path = base_dir / filename
    final_path.parent.mkdir(parents=True, exist_ok=True)

    final_json["language"] = lang_code
    # keep tracklist language in sync if present
    for tl in (final_json.get("tracklist") or []):
        if isinstance(tl, dict):
            tl["language"] = lang_code

    # harmonize mode_flag + featured; also maintain track_display_name
    def _harmonize_mode_and_feature(t: dict) -> None:
        feat = (t.get("featured_artist") or "")
        if not isinstance(feat, str):
            feat = str(feat)
        feat = feat.strip()
        flag = (t.get("mode_flag") or "").strip().upper()
        if feat and flag in ("", "SOLO"):
            t["mode_flag"] = "DUET"
        if not feat and flag in ("DUET","FEATURED"):
            t["mode_flag"] = "SOLO"
        base = t.get("track_name") or ""
        t["track_display_name"] = f"{base} (feat. {feat})" if feat else base

    for t in (final_json.get("track") or []):
        _harmonize_mode_and_feature(t)

    save_full_json_file(payload=final_json, decade=decade, filename=filename)

    # === STEP 11: summary logging (same helper)
    log_generate_json_summary(
        tracks=track_entries,
        artists=artist_entries,
        now=datetime.now(),
        category=decade,
        genre=genre,
        errors=[]
    )

    return str(final_path), len(final_json.get("track") or [])

@router.post("/generate-json/poprock/{decade}", response_model=GenerateOut)
def generate_poprock(
    decade: str = PathParam(..., description="e.g., 1980s"),
    language: str = Query("en"),
    num_pop: int = Query(45),
    num_rock: int = Query(45),
    canon_fallback_to_pop: bool = Query(True),
    persist: bool = Query(True, description="Write JSON files to disk"),
):
    """
    Generate POP and ROCK for a decade via the same end-to-end pipeline as /generate-json:
    - model candidates (pop & rock) → enrich with Spotify → build final schema
    - handle missing/replace/fill spares → reassign ranks
    - add track + artist descriptions via XAI
    - save JSON using get_json_path/save_full_json_file (same format & location)
    """
    request_id = str(uuid4())
    logger.info(
        "🎬 generate_poprock start | req=%s decade=%s lang=%s pop=%d rock=%d buffer=%d overlap_allow=%d cap=%d provider=%s",
        request_id, decade, language, num_pop, num_rock,
        BUFFER_SIZE_FIXED, OVERLAP_ALLOWANCE_FIXED, MAX_TRACKS_PER_ARTIST_FIXED,
        os.getenv("LLM_PROVIDER", "xai"),
    )

    # 1) Build prompt (fixed knobs applied)
    prompt = build_poprock_prompt(
        decade=decade,
        language=language,
        num_pop=num_pop,
        num_rock=num_rock,
        buffer_size=BUFFER_SIZE_FIXED,
        anchors_pop=[],
        anchors_rock=[],
        coverage_pop=["synthpop/new wave", "dance-pop", "adult contemporary"],
        coverage_rock=["hard rock/metal", "post-punk/new wave", "AOR", "alternative/college"],
        max_tracks_per_artist=MAX_TRACKS_PER_ARTIST_FIXED,
        canon_fallback_to_pop=canon_fallback_to_pop,
        overlap_allowance=OVERLAP_ALLOWANCE_FIXED,
    )
    logger.debug("req=%s prompt_preview=%r", request_id, prompt[:300] + ("…" if len(prompt) > 300 else ""))

    # 2) LLM → both lists
    t0 = time.perf_counter()
    try:
        raw = complete_json(prompt, provider="xai")
    except Exception as e:
        logger.exception("req=%s LLM call failed", request_id)
        raise HTTPException(502, f"LLM call failed: {e}")
    elapsed = time.perf_counter() - t0
    logger.info("✅ req=%s LLM ok in %.2fs", request_id, elapsed)

    if not isinstance(raw, dict) or "pop" not in raw or "rock" not in raw:
        logger.error("req=%s Bad LLM shape: keys=%s", request_id, list(raw.keys()) if isinstance(raw, dict) else type(raw))
        raise HTTPException(500, "Model did not return the required JSON object with 'pop' and 'rock'.")

    pop_rows = raw.get("pop") or []
    rock_rows = raw.get("rock") or []
    logger.info("req=%s counts_raw pop=%d rock=%d", request_id, len(pop_rows), len(rock_rows))

    # 3) Quick schema guard on candidate objects (before pipeline)
    def _valid(r: Dict[str, Any]) -> bool:
        return all(k in r for k in ("trackName","artistName","albumName","yearReleased"))
    pop_rows = [r for r in pop_rows if _valid(r)]
    rock_rows = [r for r in rock_rows if _valid(r)]

    # 4) Deduplicate inside each, and enforce overlap allowance at the candidate stage
    pop_before_dedupe = len(pop_rows); rock_before_dedupe = len(rock_rows)
    pop_rows = _dedupe_keep_best(pop_rows, ["importanceScore","popScore","rockScore"])
    rock_rows = _dedupe_keep_best(rock_rows, ["importanceScore","rockScore","popScore"])
    pop_rows, rock_rows, overlap = _enforce_overlap(pop_rows, rock_rows, OVERLAP_ALLOWANCE_FIXED)
    logger.info(
        "req=%s dedupe pop %d→%d rock %d→%d | overlap_after=%d",
        request_id, pop_before_dedupe, len(pop_rows), rock_before_dedupe, len(rock_rows), len(overlap)
    )

    # 5) Trim candidate sets to requested counts for the pipeline start
    pop_rows = _trim_to_n(pop_rows, num_pop, ["importanceScore","popScore","rockScore"])
    rock_rows = _trim_to_n(rock_rows, num_rock, ["importanceScore","rockScore","popScore"])

    # 6) Run the full generate_json pipeline for each genre
    saved = {}
    pop_path, pop_n = _process_genre(
        decade=decade, genre="pop", language=language,
        target_count=num_pop, candidate_rows=pop_rows, request_id=request_id
    )
    saved["pop"] = pop_path

    rock_path, rock_n = _process_genre(
        decade=decade, genre="rock", language=language,
        target_count=num_rock, candidate_rows=rock_rows, request_id=request_id
    )
    saved["rock"] = rock_path

    logger.info(
        "🏁 req=%s done | counts_before={pop:%d,rock:%d} overlap_after=%d counts_final={pop:%d,rock:%d}",
        request_id, len(raw.get("pop") or []), len(raw.get("rock") or []), len(overlap), pop_n, rock_n
    )

    return GenerateOut(
        decade=decade,
        counts_before={"pop": len(raw.get("pop") or []), "rock": len(raw.get("rock") or [])},
        overlap_after=len(overlap),
        counts_final={"pop": pop_n, "rock": rock_n},
        saved_files=saved,
    )
