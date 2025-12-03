# backend/routers/tts_intro.py
from __future__ import annotations

import logging
import time
import requests
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

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
    XAI_API_KEY,
    XAI_API_URL,
    XAI_MODEL,
    TEMPERATURE_DEFAULT,
)
from backend.utils.tts_diagnostics import (
    get_missing_tts_info,
    normalize_for_filename,
)
from backend.services.tts_prep import prepare_for_tts_es, prepare_for_tts_pt_br
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger(__name__)  # resolves to "backend.routers.tts_intro"

intro_router = APIRouter(prefix="/tts/intro")


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


_LANG_LABEL = {
    "en": "English",
    "es": "Spanish",
    "pt-BR": "Portuguese (Brazil)",
}

def _call_llm_translate_intro(en_text: str, lang: str, track_name: str, artist_name: str, rank: int | None) -> str:
    api_key = (XAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Missing XAI_API_KEY env var")

    target_label = _LANG_LABEL.get(lang, lang)
    rank_phrase = f"(rank {rank})" if rank else ""
    system = f"Translate an English radio-style song intro to {target_label}. Keep the announcer tone, concise, punchy. Keep facts identical."
    user = f"""English intro {rank_phrase}:
{en_text}

Constraints:
- Keep EXACT song/artist spellings as provided: {track_name} — {artist_name}.
- Do NOT add or remove facts.
- 1–3 sentences max. No markdown."""
    payload = {
        "model": XAI_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user",   "content": user}],
        "temperature": TEMPERATURE_DEFAULT,
        "max_tokens": 240,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_err: Any = None
    for attempt in range(3):
        try:
            r = requests.post(XAI_API_URL, headers=headers, json=payload, timeout=(10, 60))
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = r
                time.sleep(1.5 * (attempt + 1)); continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.RequestException as ex:
            last_err = ex
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f"xAI translate failed: {type(ex).__name__}: {ex}")
        except (KeyError, IndexError) as ex:
            body = getattr(last_err, 'text', '')[:300]
            raise RuntimeError(f"Unexpected xAI response shape: {ex}; body={body}")

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
    If localized text is absent, auto-translate from an English base and upsert TrackRankingLocale.intro_text.
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

    # Load rankings + relationships needed to rebuild filenames
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

    # Per-language voice / model / settings
    voice_cfg = (TTS_PROFILES.get(lang, {}).get("intro") or {})
    voice_id = voice_cfg.get("voice_id") or VOICE_ID_INTRO
    voice_settings = voice_cfg.get("settings") or {}
    model_id = voice_cfg.get("model_id") or MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))

    # Log model/voice choice
    logger.debug(
        "🎙️ Intro TTS config | lang=%s | model_id=%s | voice_id=%s | settings=%s | default_lang=%s",
        lang, model_id, voice_id, voice_settings, DEFAULT_TTS_LANGUAGE,
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

        track_name = ranking.track.track_name or ""
        artist_name = (ranking.track.artist.artist_name if ranking.track.artist else "") or "Unknown Artist"
        rank_val = int(ranking.ranking or 0)

        # Base English (fallback) intro
        en_text = (ranking.intro or "").strip()
        if not en_text:
            # Try a few common fields; else synthesize a minimal base
            for attr in ("intro_text", "intro_en", "intro_script"):
                en_text = (getattr(ranking, attr, None) or "").strip()
                if en_text:
                    break
        if not en_text:
            en_text = f"At number {rank_val or 'zero'}, '{track_name}' by {artist_name}."

        if lang == "en":
            text = en_text
        else:
            text = localized_text_by_tr.get(ranking.id, "").strip()
            if not text:
                # Translate EN → target language
                translated = _call_llm_translate_intro(en_text, lang, track_name, artist_name, rank_val)

                # Language-specific TTS prep
                if lang == "es":
                    translated = prepare_for_tts_es(
                        translated,
                        rank=rank_val,
                        track_name=track_name,
                        artist_name=artist_name,
                        strip_markdown=True,
                        number_normalize=True,
                    )
                elif lang == "pt-BR":
                    translated = prepare_for_tts_pt_br(
                        translated,
                        rank=rank_val,
                        track_name=track_name,
                        artist_name=artist_name,
                        strip_markdown=True,
                        number_normalize=True,
                    )

                # Upsert TrackRankingLocale.intro_text
                existing_row = db.exec(
                    select(TrackRankingLocale).where(
                        TrackRankingLocale.track_ranking_id == ranking.id,
                        TrackRankingLocale.language_code == lang
                    )
                ).first()
                if existing_row:
                    existing_row.intro_text = translated
                    db.add(existing_row)
                else:
                    db.add(TrackRankingLocale(
                        track_ranking_id=ranking.id,
                        language_code=lang,
                        intro_text=translated
                    ))
                text = translated

        # Defensive per-language prep (idempotent)
        if lang == "es":
            text = prepare_for_tts_es(
                text,
                rank=rank_val,
                track_name=track_name,
                artist_name=artist_name,
                strip_markdown=True,
                number_normalize=True,
            )
        elif lang == "pt-BR":
            text = prepare_for_tts_pt_br(
                text,
                rank=rank_val,
                track_name=track_name,
                artist_name=artist_name,
                strip_markdown=True,
                number_normalize=True,
            )

        items.append(
            {
                "track_id": ranking.track.id,
                "track_name": track_name,
                "artist_name": artist_name,
                "album_name": ranking.track.album_name or "TopSpot40 Intro Tracks",
                "intro": text,  # <-- text key used below
                "rank": rank_val,
                "decade": decade,
                "genre": genre,
                "language": lang,
            }
        )

        if limit is not None and len(items) >= limit:
            break

    # Commit any new/updated TrackRankingLocale rows
    try:
        db.commit()
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Commit failed while saving TrackRankingLocale.intro_text: {ex}")

    if not items:
        logger.info("🚫 No eligible tracks to synthesize (missing intro text in all candidates).")
        return {
            "generated": 0,
            "skipped": missing_text_count or len(missing_basenames_all),
            "missing_found": len(missing_basenames_all),
            "files": [],
            "message": "No eligible tracks to synthesize for requested language.",
        }

    # Generate to local disk. Your uploader (if any) can read items[i]["language"] to route to audio-<lang>/intro/.
    return generate_tts_batch(
        items=items,
        text_key="intro",
        voice_id=voice_id,
        voice_settings=voice_settings,                # ✅ forward profile settings
        output_dir=Path("data/mp3_files/track_intro_mp3_files"),
        filename_func=generate_intro_filename,
        log_prefix=f"Track Intro [{lang}]",
        overwrite=overwrite,
        play=play,
        default_language=lang,
        normalize=True,
        model_id=model_id,                            # ✅ forward model
    )
