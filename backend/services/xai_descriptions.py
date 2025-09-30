from __future__ import annotations
from typing import List, Dict, Any, Optional

import backend.config as cfg
from backend.services.xai_rank_intro import get_rank_intros_from_xai
from backend.services.xai_track_detail import get_track_details_from_xai
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai

import logging
logger = logging.getLogger(__name__)  # e.g., "backend.services.xai_descriptions"

# ─────────────────────────────────────────────────────────────────────────────
# Detail generation helpers
# ─────────────────────────────────────────────────────────────────────────────
import re

_AVOID_KEYS = ("artist_name", "artist_display_name", "album_name", "rank", "year_released")

def _detail_guideline_for(t: Dict[str, Any]) -> str:
    """
    Returns a single-line instruction for the LLM:
    - No repeating artist/album/rank/year (the intro already covers that).
    - Focus on placement/context (movie/TV), scene/mood/function.
    """
    artist = t.get("artist_display_name") or t.get("artist_name") or ""
    album  = t.get("album_name") or ""
    year   = t.get("year_released")
    # Optional metadata that might exist in your payload:
    source_title = t.get("source_title") or t.get("show_title") or t.get("movie_title")
    source_type  = t.get("source_type")  # "movie" | "tv" | "game" | etc.
    scene_hint   = t.get("scene_hint") or t.get("placement_hint")  # any custom hint you might attach

    src = ""
    if source_title and source_type:
        src = f" If relevant, refer to its role within the {source_type} '{source_title}'."
    elif source_title:
        src = f" If relevant, refer to its role within '{source_title}'."

    # We *tell* the model what to avoid and what to focus on.
    return (
        "Do NOT repeat the artist, album, rank, or year; the intro already covers those. "
        "Write 3–5 sentences focusing on the track’s context and function—"
        "e.g., how it’s used within a movie/TV scene, what mood or story beat it supports, "
        "and why it fits that placement musically or lyrically."
        + (f" {scene_hint}" if scene_hint else "")
        + src
    )

def _sanitize_detail_text(t: Dict[str, Any], text: str) -> str:
    """
    Removes lines/sentences that redundantly restate artist, album, rank, or year.
    Conservative approach: sentence-level filtering with a few targeted patterns.
    """
    if not isinstance(text, str):
        return text

    artist = (t.get("artist_display_name") or t.get("artist_name") or "").strip()
    album  = (t.get("album_name") or "").strip()
    year   = t.get("year_released")
    rank   = t.get("rank")

    # Build phrase set to check (lowercased)
    literals = set()
    if artist:
        literals.add(artist.lower())
    if album:
        literals.add(album.lower())

    # Regex patterns (case-insensitive)
    patterns = []

    # year as a bare number and in parentheses e.g. (1981)
    if isinstance(year, int):
        patterns.append(rf"\b{year}\b")
        patterns.append(rf"\(\s*{year}\s*\)")  # (1981)

    # rank mentions: "rank 1", "ranking #1", "No. 1", "#1"
    if isinstance(rank, int):
        patterns += [
            rf"\brank(?:ing)?\s*[:#]?\s*{rank}\b",
            rf"\bno\.?\s*{rank}\b",
            rf"(?:^|\s)#\s*{rank}\b",
        ]

    # “by <artist>” and “from (the) album <album>” patterns
    if artist:
        # allow punctuation between words, be flexible with whitespace
        patterns.append(rf"\bby\s+{re.escape(artist)}\b")
    if album:
        patterns.append(rf"\bfrom\s+(?:the\s+)?album\s+{re.escape(album)}\b")

    # Split into sentences and drop any that trip a rule
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: List[str] = []
    for s in sentences:
        s_l = s.lower()
        # literal contains?
        if any(lit in s_l for lit in literals):
            continue
        # regex contains?
        if any(re.search(p, s, flags=re.IGNORECASE) for p in patterns):
            continue
        kept.append(s)

    cleaned = " ".join(kept).strip()
    return cleaned if cleaned else text.strip()



def get_track_descriptions_from_xai(track_data, language, decade, genre):
    """
    BACKWARD-COMPAT SHIM for decade-genre pipeline.
    Delegates to get_collection_descriptions_from_xai so both paths share logic.

    track_data can be a dict with:
      { "tracks": [...], "track_ranking": [...] }  (optional track_ranking)
    or simply a list of track dicts.
    """
    # Deprecation via logging (instead of warnings.warn)
    logger.warning(
        "DEPRECATED: get_track_descriptions_from_xai() is kept for backward compatibility; "
        "use get_collection_descriptions_from_xai()."
    )


    # Normalize inputs
    if isinstance(track_data, dict):
        tracks = track_data.get("tracks", []) or []
        ranking = track_data.get("track_ranking")  # may be None
    else:
        tracks = track_data or []
        ranking = None

    # Reuse the same engine; use a synthetic slug for context
    slug = f"{str(decade or 'decade').lower()}_{str(genre or 'genre').lower()}"

    described = get_collection_descriptions_from_xai(
        tracks=tracks,
        language=language,
        slug=slug,
        decade=decade,
        genre=genre,
        ranking=ranking,
    )

    # Keep return shape compatible with callers that expect 'decade'/'genre'
    described.setdefault("decade", decade)
    described.setdefault("genre", genre)
    return described



def get_collection_descriptions_from_xai(
    tracks: List[Dict[str, Any]],
    *,
    language: str = "en",
    slug: str,
    decade: Optional[str] = None,
    genre: Optional[str] = None,
    ranking: Optional[List[Dict[str, Any]]] = None,   # ← expects rows: {rank, track_id?, spotify_track_id?}
) -> Dict[str, Any]:
    """
    - Works with/without decade/genre context.
    - Applies rank intros on both: (a) ranking rows, (b) each track dict.
    - Details/Artist descriptions are written onto each track.
    """
    total = len(tracks)
    logger.debug(f"🧠 STEP 9C: XAI for {total} collection track(s) | slug={slug} | lang={language}")

    # ---------- RANK INTRO ----------
    if cfg.ENABLE_RANK_INTRO:
        intro_payload = get_rank_intros_from_xai(tracks, language, decade, genre)
        intro_by_sid_rank = {}
        for tr in intro_payload.get("tracks", []):
            sid = tr.get("spotify_track_id")
            rnk = tr.get("rank")
            if sid and rnk and tr.get("_xai_intro"):
                intro_by_sid_rank[(sid, int(rnk))] = tr["_xai_intro"]

        # 1) write into ranking rows
        if isinstance(ranking, list):
            for row in ranking:
                sid = row.get("spotify_track_id")
                rnk = row.get("rank")
                if sid and rnk:
                    intro = intro_by_sid_rank.get((sid, int(rnk)))
                    if intro:
                        row["intro"] = intro

        # 2) write onto each track (self-contained JSON)
        index = {(t.get("spotify_track_id"), int(t.get("rank")) if t.get("rank") is not None else None): t for t in tracks}
        for (sid, rnk), intro in intro_by_sid_rank.items():
            t = index.get((sid, rnk))
            if t is not None:
                t["intro"] = intro  # use `intro` to match your decade-genre schema


    if cfg.ENABLE_TRACK_DETAIL:
        # ---------- TRACK DETAIL ----------
        # Hint the detail prompt about the collection theme (e.g., "Power Ballads")
        for t in tracks:
            t["_genre_context"] = genre or (slug.replace("_", " ").title() if slug else None)
            # NEW: give each track a clear, one-line instruction for detail style
            t["_detail_guidelines"] = _detail_guideline_for(t)

        get_track_details_from_xai(tracks, language)   # writes t["detail"]

    # SANITIZE: remove any repeated artist/album/rank/year from the detail
    for t in tracks:
        if isinstance(t.get("detail"), str) and t["detail"].strip():
            t["detail"] = _sanitize_detail_text(t, t["detail"])

    # --- Normalize detail into a single canonical key ---
    DETAIL_ALIASES = [
        "detail",
        "detail_en",
        "description",
        "trackDetail",
        "track_detail",
        "detailText",
        "trackDetailText",
        "long_detail",
        "longDescription",
        "long_description",
        "trackDescription",
        "track_description",
        # a few extras to be safe:
        "detail_en_us",
        "detail_text",
        "track_long_text",
        "narrative",
    ]

    # Optional: allow a minimal synthetic fallback line when XAI returns nothing
    DETAIL_FALLBACK_SENTENCE = getattr(cfg, "DETAIL_FALLBACK_SENTENCE", True)

    for t in tracks:
        if not isinstance(t, dict):
            continue
        if isinstance(t.get("detail"), str) and t["detail"].strip():
            continue  # already set (and sanitized above)

        picked = None
        for dk in DETAIL_ALIASES:
            dv = t.get(dk)
            if isinstance(dv, str) and dv.strip():
                picked = dv.strip()
                break

        if picked:
            t["detail"] = _sanitize_detail_text(t, picked)
        elif DETAIL_FALLBACK_SENTENCE:
            # Context-first, no repeats of artist/album/year/rank
            ctx = (genre or (slug.replace("_", " ").title() if slug else "") or "this collection")
            hint = t.get("scene_hint") or t.get("placement_hint") or ""
            # If you have source metadata, nod to it without naming year/artist/album:
            src_title = t.get("source_title") or t.get("show_title") or t.get("movie_title")
            src_type = t.get("source_type")
            src_part = f" within the {src_type} '{src_title}'" if (src_title and src_type) else (
                f" in '{src_title}'" if src_title else "")
            t["detail"] = (
                f"A context piece that supports the {ctx.lower()} vibe{src_part}, "
                f"underscoring the scene’s mood and narrative beat{', ' + hint if hint else ''}."
            )

    # ---------- ARTIST DETAIL ----------
    if cfg.ENABLE_ARTIST_DETAIL:
        get_artist_descriptions_from_xai(tracks, language)  # writes t["artistDetail"] or similar

    # cleanup transient
    for t in tracks:
        t.pop("_xai_intro", None)
        t.pop("_genre_context", None)  # remove prompt-only hint
        t.pop("_detail_guidelines", None)  # NEW

    # Debug: how many details did we actually fill?
    filled = sum(1 for t in tracks if isinstance(t.get("detail"), str) and t["detail"].strip())
    logger.debug(f"🧠 STEP 9C: detail filled for {filled}/{len(tracks)} tracks")

    return {
        "language": language,
        "slug": slug,
        "decade": decade,
        "genre": genre,
        "tracks": tracks,
        "track_ranking": ranking or [],
    }
