# backend/routers/generate_poprock.py
from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Tuple
import json, re, time, os, logging
from uuid import uuid4
from pathlib import Path as FsPath

from backend.services.prompt_poprock import build_poprock_prompt
from backend.services.llm_client import complete_json  # def complete_json(prompt:str) -> dict

router = APIRouter(prefix="", tags=["generate-json"])
logger = logging.getLogger(__name__)

# ---- Normalization helpers ----
def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = re.sub(r"\s+", " ", s)
    return s

def _key(row: Dict[str, Any]) -> Tuple[str, str]:
    # Remove redundant parentheses warning by returning tuple directly
    return _norm(row.get("artistName")), _norm(row.get("trackName"))

def _dedupe_keep_best(rows: List[Dict[str, Any]], score_fields: List[str]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str,str], Dict[str, Any]] = {}
    for r in rows:
        k = _key(r)
        prev = best.get(k)
        if not prev:
            best[k] = r
            continue
        # keep the one with better (importanceScore, then pop/rockScore)
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

    # If too many overlaps, remove extras from ROCK (pop wins ties) by lowest importance first
    overlap_rows_rock = [r for r in rock_rows if _key(r) in overlap]
    overlap_rows_rock_sorted = sorted(overlap_rows_rock, key=lambda r: (r.get("importanceScore",0), r.get("rockScore",0)))
    to_remove = len(overlap) - allowance
    remove_set = {_key(r) for r in overlap_rows_rock_sorted[:to_remove]}
    rock_rows = [r for r in rock_rows if _key(r) not in remove_set]

    # recompute final overlap list after removals
    final_overlap = list({_key(r) for r in pop_rows} & {_key(r) for r in rock_rows})
    return pop_rows, rock_rows, final_overlap

class GenerateOut(BaseModel):
    decade: str
    counts_before: Dict[str, int]
    overlap_after: int
    counts_final: Dict[str, int]
    saved_files: Dict[str, str]

@router.post("/generate-json/poprock/{decade}", response_model=GenerateOut)
def generate_poprock(
    decade: str = PathParam(..., description="e.g., 1980s"),
    language: str = Query("en"),
    num_pop: int = Query(45),
    num_rock: int = Query(45),
    buffer_size: int = Query(15),
    overlap_allowance: int = Query(0),
    canon_fallback_to_pop: bool = Query(True),
    # Optional knobs you can omit in most calls:
    max_tracks_per_artist: int = Query(1),
    persist: bool = Query(True, description="Write JSON files to disk"),
    out_dir: str = Query("json", description="Base folder for saved files"),
):
    """
    Generate both POP and ROCK lists together for a decade, enforce overlap policy,
    downselect to target sizes, and (optionally) save to two JSON files.
    """
    request_id = str(uuid4())
    logger.info(
        "🎬 generate_poprock start | req=%s decade=%s lang=%s pop=%d rock=%d buffer=%d overlap_allow=%d cap=%d persist=%s out_dir=%s provider=%s",
        request_id, decade, language, num_pop, num_rock, buffer_size, overlap_allowance,
        max_tracks_per_artist, persist, out_dir, os.getenv("LLM_PROVIDER", "openai"),
    )

    # 1) Build prompt
    prompt = build_poprock_prompt(
        decade=decade,
        language=language,
        num_pop=num_pop,
        num_rock=num_rock,
        buffer_size=buffer_size,
        anchors_pop=[],
        anchors_rock=[],
        coverage_pop=["synthpop/new wave", "dance-pop", "adult contemporary"],  # tweak per decade
        coverage_rock=["hard rock/metal", "post-punk/new wave", "AOR", "alternative/college"],
        max_tracks_per_artist=max_tracks_per_artist,
        canon_fallback_to_pop=canon_fallback_to_pop,
        overlap_allowance=overlap_allowance,
    )
    logger.debug("req=%s prompt_preview=%r", request_id, prompt[:300] + ("…" if len(prompt) > 300 else ""))

    # 2) Call your LLM (must return a dict with keys "pop" and "rock")
    t0 = time.perf_counter()
    try:
        raw = complete_json(prompt)   # <- implement in backend.services.llm_client
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

    # 3) Basic schema guard (ignore extras but require core fields)
    def _valid(r: Dict[str, Any]) -> bool:
        return all(k in r for k in ("trackName","artistName","albumName","yearReleased","importanceScore","popScore","rockScore"))

    pop_rows = [r for r in pop_rows if _valid(r)]
    rock_rows = [r for r in rock_rows if _valid(r)]
    counts_before = {"pop": len(pop_rows), "rock": len(rock_rows)}
    logger.info("req=%s counts_after_schema pop=%d rock=%d", request_id, counts_before["pop"], counts_before["rock"])

    # 4) De-dupe WITHIN each list (keep best by importance + score), then enforce cross-list overlap policy
    pop_before_dedupe = len(pop_rows); rock_before_dedupe = len(rock_rows)
    pop_rows = _dedupe_keep_best(pop_rows, ["importanceScore","popScore","rockScore"])
    rock_rows = _dedupe_keep_best(rock_rows, ["importanceScore","rockScore","popScore"])
    logger.info(
        "req=%s dedupe pop: %d→%d, rock: %d→%d",
        request_id, pop_before_dedupe, len(pop_rows), rock_before_dedupe, len(rock_rows)
    )

    pop_rows, rock_rows, overlap = _enforce_overlap(pop_rows, rock_rows, overlap_allowance)
    logger.info("req=%s overlap_after_enforcement=%d (allowance=%d)", request_id, len(overlap), overlap_allowance)
    logger.debug("req=%s overlap_examples=%s", request_id, overlap[:5])

    # 5) Downselect to requested sizes
    pop_rows = _trim_to_n(pop_rows, num_pop, ["importanceScore","popScore","rockScore"])
    rock_rows = _trim_to_n(rock_rows, num_rock, ["importanceScore","rockScore","popScore"])
    logger.info("req=%s trimmed pop=%d rock=%d", request_id, len(pop_rows), len(rock_rows))

    # 6) Renumber ranks 1..N (optional, since you also rank later during upsert)
    for i, r in enumerate(pop_rows, start=1):
        r["rank"] = i
    for i, r in enumerate(rock_rows, start=1):
        r["rank"] = i

    # 7) Persist to files (same naming your upsert expects)
    saved = {}
    if persist:
        try:
            base = FsPath(out_dir) / decade
            base.mkdir(parents=True, exist_ok=True)

            pop_path = base / f"{decade}_pop_{language}.json"
            rock_path = base / f"{decade}_rock_{language}.json"

            with pop_path.open("w", encoding="utf-8") as f:
                json.dump({"genre": "pop", "category": decade, "track_ranking": pop_rows}, f, ensure_ascii=False, indent=2)
            with rock_path.open("w", encoding="utf-8") as f:
                json.dump({"genre": "rock", "category": decade, "track_ranking": rock_rows}, f, ensure_ascii=False, indent=2)

            saved = {"pop": str(pop_path), "rock": str(rock_path)}
            logger.info("req=%s saved pop=%s rock=%s", request_id, saved["pop"], saved["rock"])
        except Exception:
            logger.exception("req=%s persist failed (out_dir=%s)", request_id, out_dir)
            raise HTTPException(500, "Failed to save generated JSON files.")

    logger.info(
        "🏁 req=%s done | counts_before=%s overlap_after=%d counts_final={pop:%d,rock:%d}",
        request_id, counts_before, len(overlap), len(pop_rows), len(rock_rows)
    )

    return GenerateOut(
        decade=decade,
        counts_before=counts_before,
        overlap_after=len(overlap),
        counts_final={"pop": len(pop_rows), "rock": len(rock_rows)},
        saved_files=saved,
    )
