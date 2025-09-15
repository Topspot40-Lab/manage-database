from __future__ import annotations
from typing import List, Dict, Any, Optional

from backend.config import ENABLE_RANK_INTRO, ENABLE_TRACK_DETAIL, ENABLE_ARTIST_DETAIL
from backend.services.xai_rank_intro import get_rank_intros_from_xai
from backend.services.xai_track_detail import get_track_details_from_xai
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai

import logging
logger = logging.getLogger(__name__)  # e.g., "backend.services.xai_descriptions"

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
    if ENABLE_RANK_INTRO:
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

    # ---------- TRACK DETAIL ----------
    if ENABLE_TRACK_DETAIL:
        get_track_details_from_xai(tracks, language)   # writes t["detail"]

    # ---------- ARTIST DETAIL ----------
    if ENABLE_ARTIST_DETAIL:
        get_artist_descriptions_from_xai(tracks, language)  # writes t["artistDetail"] or similar

    # cleanup transient
    for t in tracks:
        t.pop("_xai_intro", None)

    return {
        "language": language,
        "slug": slug,
        "decade": decade,
        "genre": genre,
        "tracks": tracks,
        "track_ranking": ranking or [],
    }
