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
