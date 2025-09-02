# backend/routers/tts_intro.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select
from backend.services.tts_prep import prepare_for_tts_es, prepare_for_tts_pt_br

from backend.database import get_db
from backend.models.dbmodels import (
    TrackRanking,
    Track,
    DecadeGenre,
    TrackRankingLocale,
)
from backend.config import (
    VOICE_ID_INTRO,
    TTS_PROFILES,
    MODEL_BY_LANG,
    DEFAULT_TTS_LANGUAGE,
)
from backend.utils.tts_diagnostics import (
    get_missing_tts_info,
    normalize_for_filename,
)
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger(__name__)  # resolves to "backend.routers.tts_intro"

intro_router = APIRouter(
    prefix="/tts/intro",
    tags=["TTS - Intro"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def generate_intro_filename(item: Dict[str, Any]) -> str:
    """
    Local filename: <decade>_<genre>_<rank:02>.mp3  (no 'intro/' prefix)
    """
    decade = normalize_for_filename(item["decade"])
    genre = normalize_for_filename(item["genre"])
    return f"{decade}_{genre}_{int(item['rank']):02}.mp3"


def _parse_count_to_limit(count_param: Optional[int]) -> Optional[int]:
    """
    None or <0 => unlimited (None); 0 => 0; >0 => that number
    """
    try:
        raw = int(count_param) if count_param is not None else -1
    except (TypeError, ValueError):
        raw = -1
    return None if raw < 0 else raw


def _basename_list(missing_items: Iterable[str]) -> List[str]:
    """
    From diagnostics like 'intro/1960s_latin_global_36.mp3',
    return ordered, de-duplicated basenames like '1960s_latin_global_36.mp3'.
    """
    seen: Set[str] = set()
    ordered: List[str] = []
    for s in missing_items:
        if not s:
            continue
        name = s.strip()
        # strip a leading 'intro/' if present
        if "/" in name:
            name = name.rsplit("/", 1)[-1]
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint (LOCAL DISK ONLY)
# ─────────────────────────────────────────────────────────────────────────────

@intro_router.post("/by-missing")
async def generate_missing_intro_tts(
    count: int = Query(
        -1, description="Number of missing intro TTS files to generate. Use -1 for all."
    ),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    language: str = Query(
        "en", regex="^(en|es|pt-BR|ptbr|pt-br)$", description="Target language for TTS (en|es|pt-BR)"
    ),
    db: Session = Depends(get_db),
):
    """
    Find missing INTRO MP3s and generate them for the requested language.
    Filenames are unchanged; callers/uploader should route by language (audio-<lang>/intro/).
    """

    # normalize language key (defensive)
    lang = "pt-BR" if language.lower() in ("ptbr", "pt-br") else language

    limit = _parse_count_to_limit(count)
    logger.info("🧠 Generating up to %s missing intro TTS files [lang=%s]", count, lang)

    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=True,
        check_detail_mp3=False,
        check_artist_mp3=False,
        language=lang,  # if diagnostics are language-aware; harmless otherwise
    )

    missing_keys = (diagnostics.get("missing_mp3", {}).get("track_intro", []) or [])
    missing_basenames_all = _basename_list(missing_keys)
    if not missing_basenames_all:
        return {"generated": 0, "skipped": 0, "missing_found": 0, "files": []}

    chosen_basenames: List[str] = (
        missing_basenames_all if limit is None else missing_basenames_all[:limit]
    )
    chosen_set = set(chosen_basenames)

    # Load the universe of rankings with relationships needed to rebuild filenames
    rankings = db.exec(
        select(TrackRanking).options(
            selectinload(TrackRanking.track),
            selectinload(TrackRanking.track).selectinload(Track.artist),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.decade),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.genre),
        )
    ).all()

    # If lang != en, prefetch localized intros into a dict: {tr_id: intro_text}
    localized_text_by_tr: Dict[int, str] = {}
    if lang != "en":
        loc_rows = db.exec(
            select(TrackRankingLocale).where(TrackRankingLocale.language_code == lang)
        ).all()
        for loc in loc_rows:
            if loc.track_ranking_id and (loc.intro_text or "").strip():
                localized_text_by_tr[loc.track_ranking_id] = loc.intro_text.strip()


    # Pick the per-language voice id (falls back to VOICE_ID_INTRO if missing)
    voice_id = (
            (TTS_PROFILES.get(lang, {}).get("intro", {}) or {}).get("voice_id")
            or VOICE_ID_INTRO
    )
    model_id = MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))

    # ── NEW: log model/voice choice + fallback state ────────────────────────────
    primary_model = MODEL_BY_LANG.get(lang)
    primary_voice = (TTS_PROFILES.get(lang, {}).get("intro", {}) or {}).get("voice_id")
    used_model_fb = primary_model is None
    used_voice_fb = primary_voice is None and VOICE_ID_INTRO is not None

    logger.debug(
        "🎙️ Intro TTS config | lang=%s | model_id=%s%s | voice_id=%s%s | default_lang=%s",
        lang,
        model_id, " [fallback]" if used_model_fb else "",
        voice_id, " [fallback]" if used_voice_fb else "",
        DEFAULT_TTS_LANGUAGE,
    )

    if model_id is None:
        logger.error(
            "No TTS model configured for lang=%r and default=%r. MODEL_BY_LANG keys: %s",
            lang, DEFAULT_TTS_LANGUAGE, list(MODEL_BY_LANG.keys())
        )
        return {
            "generated": 0, "skipped": 0, "missing_found": 0, "files": [],
            "error": f"MODEL_BY_LANG has no entry for '{lang}' nor default '{DEFAULT_TTS_LANGUAGE}'"
        }

    items: List[Dict[str, Any]] = []
    missing_text_count = 0

    for ranking in rankings:
        decade = ranking.decade_genre.decade.decade_name
        genre = ranking.decade_genre.genre.genre_name
        basename = generate_intro_filename(
            {"decade": decade, "genre": genre, "rank": ranking.ranking}
        )

        if basename not in chosen_set:
            continue

        if lang == "en":
            text = (ranking.intro or "").strip()
        else:
            text = localized_text_by_tr.get(ranking.id, "").strip()

        if not text:
            missing_text_count += 1
            continue

        items.append(
            {
                "track_id": ranking.track.id,
                "track_name": ranking.track.track_name,
                "artist_name": (
                    ranking.track.artist.artist_name if ranking.track.artist else "Unknown Artist"
                ),
                "album_name": ranking.track.album_name or "TopSpot40 Intro Tracks",
                "intro": text,  # <-- text key used below
                "rank": ranking.ranking,
                "decade": decade,
                "genre": genre,
                "language": lang,  # <-- downstream/bucket router can use this
                "model_id": model_id,  # <-- optional: if your generator supports it
            }
        )

        if limit is not None and len(items) >= limit:
            break

    if not items:
        return {
            "generated": 0,
            "skipped": missing_text_count,
            "missing_found": len(missing_basenames_all),
            "files": [],
            "message": "No eligible tracks to synthesize for requested language.",
        }
    # ── FINAL, DEFENSIVE TTS PREP (per item) ─────────────────────────────────────
    # Idempotent: safe for both old rows (pre-change) and new rows (already clean)
    for it in items:
        if it.get("language") == "es":
            it["intro"] = prepare_for_tts_es(
                it["intro"],
                rank=int(it["rank"]),
                track_name=it["track_name"],
                artist_name=it["artist_name"],
                strip_markdown=True,  # strip any lingering inline markdown
                number_normalize=True,  # 1→uno, 50→cincuenta, etc.
            )
        elif it.get("language") == "pt-BR":
            it["intro"] = prepare_for_tts_pt_br(
                it["intro"],
                rank=int(it["rank"]),
                track_name=it["track_name"],
                artist_name=it["artist_name"],
                strip_markdown=True,  # strip any lingering inline markdown
                number_normalize=True,  # 1→um, 50→cinquenta, etc.
            )

    # Generate to local disk. Your uploader (if any) can read items[i]["language"]
    # to route to audio-<lang>/intro/ in object storage.
    return generate_tts_batch(
        items=items,
        text_key="intro",
        voice_id=voice_id,
        output_dir=Path("data/mp3_files/track_intro_mp3_files"),
        filename_func=generate_intro_filename,
        log_prefix=f"Track Intro [{lang}]",
        overwrite=overwrite,
        play=play,
        default_language=lang,
        normalize=True,
        # If your generate_tts_batch supports these kwargs, pass them; else they’re ignored:
        # model_id=model_id,
        # bucket_lang=lang,   # e.g., so the uploader stores to audio-es/intro/ or audio-ptbr/intro/
    )
