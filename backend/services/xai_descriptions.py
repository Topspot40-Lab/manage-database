from __future__ import annotations
from typing import List, Dict, Any, Optional

import backend.config as cfg
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

    # ---------- TRACK DETAIL ----------
    # Hint the detail prompt about the collection theme (e.g., "Power Ballads")
    for t in tracks:
        t["_genre_context"] = genre or (slug.replace("_", " ").title() if slug else None)

    if cfg.ENABLE_TRACK_DETAIL:
        get_track_details_from_xai(tracks, language)   # writes t["detail"]
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
            continue  # already set

        picked = None
        for dk in DETAIL_ALIASES:
            dv = t.get(dk)
            if isinstance(dv, str) and dv.strip():
                picked = dv.strip()
                break

        if picked:
            t["detail"] = picked
        elif DETAIL_FALLBACK_SENTENCE:
            # Conservative, single-line fallback using available metadata + theme
            title  = (t.get("track_name") or t.get("title") or "This track")
            artist = (t.get("artist_name") or t.get("artistName") or "the artist")
            year   = (t.get("year_released") or t.get("year") or "an unknown year")
            album  = (t.get("album_name") or t.get("albumName") or "an unknown album")
            ctx    = (genre or (slug.replace("_", " ").title() if slug else "") or "this collection")
            t["detail"] = (
                f"{title} by {artist}, from '{album}' ({year}), "
                f"fits the spirit of {ctx} with enduring appeal."
            )


    # ---------- ARTIST DETAIL ----------
    if cfg.ENABLE_ARTIST_DETAIL:
        get_artist_descriptions_from_xai(tracks, language)  # writes t["artistDetail"] or similar

    # cleanup transient
    for t in tracks:
        t.pop("_xai_intro", None)
        t.pop("_genre_context", None)  # remove prompt-only hint

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
