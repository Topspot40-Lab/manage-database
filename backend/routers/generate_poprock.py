# backend/routes/generate_poprock.py
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Tuple
import json, re
from pathlib import Path

from backend.services.prompt_poprock import build_poprock_prompt
# ⬇️ Replace this with your actual LLM client
from backend.services.llm_client import complete_json  # def complete_json(prompt:str) -> dict

router = APIRouter(prefix="", tags=["generate-json"])

# ---- Normalization helpers ----
def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = re.sub(r"\s+", " ", s)
    return s

def _key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (_norm(row.get("artistName")), _norm(row.get("trackName")))

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
    decade: str = Path(..., description="e.g., 1980s"),
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

    # 2) Call your LLM (must return a dict with keys "pop" and "rock")
    try:
        raw = complete_json(prompt)   # <- implement in backend.services.llm_client
    except Exception as e:
        raise HTTPException(502, f"LLM call failed: {e}")

    if not isinstance(raw, dict) or "pop" not in raw or "rock" not in raw:
        raise HTTPException(500, "Model did not return the required JSON object with 'pop' and 'rock'.")

    pop_rows = raw.get("pop") or []
    rock_rows = raw.get("rock") or []

    # 3) Basic schema guard (ignore extras but require core fields)
    def _valid(r: Dict[str, Any]) -> bool:
        return all(k in r for k in ("trackName","artistName","albumName","yearReleased","importanceScore","popScore","rockScore"))

    pop_rows = [r for r in pop_rows if _valid(r)]
    rock_rows = [r for r in rock_rows if _valid(r)]

    counts_before = {"pop": len(pop_rows), "rock": len(rock_rows)}

    # 4) De-dupe WITHIN each list (keep best by importance + score), then enforce cross-list overlap policy
    pop_rows = _dedupe_keep_best(pop_rows, ["importanceScore","popScore","rockScore"])
    rock_rows = _dedupe_keep_best(rock_rows, ["importanceScore","rockScore","popScore"])
    pop_rows, rock_rows, overlap = _enforce_overlap(pop_rows, rock_rows, overlap_allowance)

    # 5) Downselect to requested sizes
    pop_rows = _trim_to_n(pop_rows, num_pop, ["importanceScore","popScore","rockScore"])
    rock_rows = _trim_to_n(rock_rows, num_rock, ["importanceScore","rockScore","popScore"])

    # 6) Renumber ranks 1..N (optional, since you also rank later during upsert)
    for i, r in enumerate(pop_rows, start=1):
        r["rank"] = i
    for i, r in enumerate(rock_rows, start=1):
        r["rank"] = i

    # 7) Persist to files (same naming your upsert expects)
    saved = {}
    if persist:
        base = Path(out_dir) / decade
        base.mkdir(parents=True, exist_ok=True)

        pop_path = base / f"{decade}_pop_{language}.json"
        rock_path = base / f"{decade}_rock_{language}.json"

        with pop_path.open("w", encoding="utf-8") as f:
            json.dump({"genre": "pop", "category": decade, "track_ranking": pop_rows}, f, ensure_ascii=False, indent=2)
        with rock_path.open("w", encoding="utf-8") as f:
            json.dump({"genre": "rock", "category": decade, "track_ranking": rock_rows}, f, ensure_ascii=False, indent=2)

        saved = {"pop": str(pop_path), "rock": str(rock_path)}

    return GenerateOut(
        decade=decade,
        counts_before=counts_before,
        overlap_after=len(overlap),
        counts_final={"pop": len(pop_rows), "rock": len(rock_rows)},
        saved_files=saved,
    )









# backend/services/prompt_poprock.py
from typing import List, Dict, Optional
from backend.config import SPOTIFY_BLACKLIST

def build_poprock_prompt(
    decade: str,
    language: str,
    num_pop: int,
    num_rock: int,
    buffer_size: int = 15,
    anchors_pop: Optional[List[Dict]] = None,   # [{"artistName":"U2","trackName":"With or Without You"}, ...]
    anchors_rock: Optional[List[Dict]] = None,
    coverage_pop: Optional[List[str]] = None,   # ["synthpop/new wave","dance-pop","AC ballads"]
    coverage_rock: Optional[List[str]] = None,  # ["hard rock/metal","post-punk/new wave","AOR","alt/college"]
    max_tracks_per_artist: int = 1,
    canon_fallback_to_pop: bool = True,
    overlap_allowance: int = 0,  # 0 = no overlaps allowed
) -> str:
    """
    Ask the model to return BOTH lists together: {"pop":[...], "rock":[...]}
    with NO (or limited) overlap, plus meta fields for triage.
    """
    def fmt_anchors(rows):
        rows = rows or []
        return "\n".join(
            f'- "{r.get("trackName")}" by {r.get("artistName")}'
            for r in rows if r.get("trackName") and r.get("artistName")
        ) or "(none)"

    def fmt_lines(rows):
        rows = rows or []
        return "\n".join(f"- {x}" for x in rows) or "(none)"

    pop_prompted = num_pop + buffer_size
    rock_prompted = num_rock + buffer_size

    anchors_pop_lines = fmt_anchors(anchors_pop)
    anchors_rock_lines = fmt_anchors(anchors_rock)
    coverage_pop_lines = fmt_lines(coverage_pop)
    coverage_rock_lines = fmt_lines(coverage_rock)

    blacklist_line = ", ".join(name.title() for name in sorted(SPOTIFY_BLACKLIST))

    return f"""
Generate BOTH lists for the {decade} decade in a single JSON object with EXACT lengths:
{{
  "pop":  [ ... exactly {pop_prompted} objects ... ],
  "rock": [ ... exactly {rock_prompted} objects ... ]
}}

Each object MUST include:
- rank (integer)
- trackName (string)
- artistName (string)
- albumName (string) ← original official album, or "Single" if first issued as a single only
- yearReleased (integer)
- importanceScore (integer 1–100) ← overall historical/canonical weight
- popScore (integer 0–3) ← apply the POP rubric
- rockScore (integer 0–3) ← apply the ROCK rubric

General rules:
- Use {language}-speaking audience assumptions and era-accurate genre definitions.
- Include ONLY artists active in the {decade}. EXCLUDE retro/modern pastiches from other decades.
- Preserve diacritics and official capitalization.
- TTS: never use "#" for ranks; when referencing a rank in text, say "number {{rank}}".
- Year must fall within the decade. Album name should be the first official album carrying the track, or "Single" if non-album at first issue.
- Avoid duplicates, re-recordings, live-only versions, and posthumous remixes unless they are the canonical hit.

POP — Separation Rules (vs Rock):
- Mainstream, cross-format hits with pop-oriented production (hook-first writing, prominent vocals, polished mixes, dance/synth/AC radio appeal).
- Prioritize Hot 100/Radio Songs/Adult Contemporary leaders; treat Mainstream/Album Rock identity as a negative signal.
- EXCLUDE hard rock, heavy guitar-distortion leads, extended rock solos, power-trio aesthetics.
- Gray areas: keep synthpop/new wave with strong Hot 100 performance; dance-pop; pop-R&B hybrids.
- Disambiguation rubric (internal): keep only if POP score > ROCK score.

ROCK — Separation Rules (vs Pop):
- Guitar/band-centric records rooted in rock scenes (AOR, hard/alt/indie, punk/post-punk, metal, etc.).
- Prioritize Mainstream/Album Rock and rock-press canons (Hot 100 supportive but not determinative).
- EXCLUDE pure dance-pop, polished AC ballads, producer-led pop projects.
- Gray areas: guitar-led new wave/post-punk; hard rock/metal; alternative/college rock; grunge; punk.
- Disambiguation rubric (internal): keep only if ROCK score > POP score.

Artist exclusivity & diversity:
- Prefer artists whose core identity aligns with the chosen list.
- Do not include more than {max_tracks_per_artist} track(s) by the same primary artist in any single list unless absolutely essential.

Balance rule:
- Avoid over-concentrating on a single substyle; aim for balance across the decade's representative substyles for each genre.

Coverage guidance (not quotas):
- POP coverage targets:
{coverage_pop_lines}
- ROCK coverage targets:
{coverage_rock_lines}

Anchors (must-keep when valid; do NOT fabricate):
- POP anchors:
{anchors_pop_lines}
- ROCK anchors:
{anchors_rock_lines}
If an anchor clearly violates genre/decade rules, omit it; otherwise include it and reflect its canonical status with a high importanceScore.

Overlap policy:
- Cross-list overlap allowance: {overlap_allowance} track(s) maximum across POP and ROCK combined.
- If a widely recognized, decade-defining single risks exclusion due to POP/ROCK separation, prefer including it in POP to avoid omission (canonical fallback to POP: {"ENABLED" if canon_fallback_to_pop else "DISABLED"}).

Spotify availability:
- Do NOT include any artist whose catalog is missing or restricted on Spotify.
- Exclude these known unavailable artists: {blacklist_line}.
- When in doubt, omit artists that do not reliably appear in Spotify search or are unavailable for playback.

Output contract:
- Return ONLY a single valid JSON object with keys "pop" and "rock" and exactly the specified counts (no markdown, no prose).
"""
