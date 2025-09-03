# backend/routers/tts_detail.py
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, Optional, Set, Any, List, Dict, Literal

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models.dbmodels import Track, TrackLocale
from backend.config import (
    VOICE_ID_TRACK,
    TTS_PROFILES,
    MODEL_BY_LANG,
    DEFAULT_TTS_LANGUAGE,
    XAI_API_KEY,
    XAI_API_URL,
    XAI_MODEL,
    TEMPERATURE_DEFAULT,
)
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch
from backend.services.tts_prep import prepare_for_tts_es, prepare_for_tts_pt_br

import requests

logger = logging.getLogger("tts_logger")

detail_router = APIRouter(
    prefix="/tts/detail",
    tags=["TTS - Track Detail"]
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def generate_detail_filename(item: Dict[str, str]) -> str:
    return f"{item['spotify_track_id']}.mp3"

def _parse_count_to_limit(count_param: Optional[int]) -> Optional[int]:
    try:
        raw = int(count_param) if count_param is not None else -1
    except (TypeError, ValueError):
        raw = -1
    return None if raw < 0 else raw

def _spotify_id_from(x: Any) -> Optional[str]:
    if isinstance(x, str):
        return x.strip() or None
    if isinstance(x, dict):
        return x.get("spotify_track_id") or x.get("track_spotify_id")
    sid = getattr(x, "spotify_track_id", None)
    if sid:
        return sid
    track_obj = getattr(x, "track", None)
    if track_obj:
        return getattr(track_obj, "spotify_track_id", None)
    return None

def _collect_missing_spotify_ids(missing_items: Iterable[Any]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for it in missing_items:
        sid = _spotify_id_from(it)
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered

_LANG_LABEL = {
    "en": "English",
    "es": "Spanish",
    "pt-BR": "Portuguese (Brazil)",
}

def _call_llm_translate_detail(en_text: str, lang: str, track_name: str, artist_name: str) -> str:
    api_key = (XAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Missing XAI_API_KEY env var")

    target_label = _LANG_LABEL.get(lang, lang)
    system = f"Translate English to {target_label}. Natural, concise, announcer tone. Keep facts identical."
    user = f"""English detail:
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
        "max_tokens": 320,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_err: Any = None
    for attempt in range(3):
        try:
            r = requests.post(XAI_API_URL, headers=headers, json=payload, timeout=(10, 60))
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = r
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.RequestException as ex:
            last_err = ex
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"xAI translate failed: {type(ex).__name__}: {ex}")
        except (KeyError, IndexError) as ex:
            body = getattr(last_err, 'text', '')[:300]
            raise RuntimeError(f"Unexpected xAI response shape: {ex}; body={body}")

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint (LOCAL DISK ONLY)
# ─────────────────────────────────────────────────────────────────────────────
@detail_router.post("/by-missing")
async def generate_missing_detail_tts(
    count: int = Query(-1, description="Number of missing detail TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    language: Literal["en", "es", "pt-BR", "ptbr", "pt-br"] = Query("en", description="Target language for TTS (en|es|pt-BR)"),
    db: Session = Depends(get_db)
):
    """
    Finds missing DETAIL MP3s by spotify_track_id (from diagnostics),
    ensures localized detail text exists for ES/PT-BR (translate+upsert when absent),
    and generates MP3s to local disk.
    """
    lang = "pt-BR" if language.lower() in ("ptbr", "pt-br") else language

    limit = _parse_count_to_limit(count)
    logger.info("🧠 Generating up to %s missing detail TTS files [lang=%s] (negative → unlimited)", count, lang)

    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=False,
        check_detail_mp3=True,
        check_artist_mp3=False,
        language=lang,
    )
    missing_diag = diagnostics.get("missing_mp3", {}).get("track_detail", []) or []
    missing_sids_all = _collect_missing_spotify_ids(missing_diag)

    logger.info("🧮 Missing detail MP3s detected (pre-limit): %d", len(missing_sids_all))
    if not missing_sids_all:
        logger.info("✅ Nothing to generate; all detail MP3s present.")
        return {"generated": 0, "skipped": 0, "missing_found": 0, "files": []}

    missing_sids = missing_sids_all[:limit] if limit is not None else missing_sids_all
    if not missing_sids:
        logger.info("➡️ Limit yielded 0 items; nothing to do.")
        return {"generated": 0, "skipped": 0, "missing_found": len(missing_sids_all), "files": []}

    tracks: List[Track] = []
    if missing_sids:
        q = (
            select(Track)
            .where(Track.spotify_track_id.in_(missing_sids))
            .options(selectinload(Track.artist))
        )
        tracks = db.exec(q).all()

    by_sid = {t.spotify_track_id: t for t in tracks}
    not_found = [sid for sid in missing_sids if sid not in by_sid]
    if not_found:
        logger.warning("⚠️ %d Spotify IDs not found in Track table (first few): %s",
                       len(not_found), not_found[:5])

    # Prefetch existing locales for this language
    localized_by_track_id: Dict[int, str] = {}
    if lang != "en":
        track_ids = [t.id for t in tracks]
        if track_ids:
            loc_rows = db.exec(
                select(TrackLocale)
                .where(TrackLocale.language_code == lang)
                .where(TrackLocale.track_id.in_(track_ids))
            ).all()
        else:
            loc_rows = []
        for loc in loc_rows:
            if loc.track_id and (loc.detail_text or "").strip():
                localized_by_track_id[loc.track_id] = loc.detail_text.strip()

    items: List[Dict[str, Any]] = []
    missing_text_count = 0

    for sid in missing_sids:
        t = by_sid.get(sid)
        if not t:
            continue

        track_name = t.track_name or ""
        artist_name = (t.artist.artist_name if t.artist else "") or "Unknown Artist"

        if lang == "en":
            base_text = (t.detail or "").strip()
            if not base_text:
                missing_text_count += 1
                continue
            text = base_text
        else:
            existing = localized_by_track_id.get(t.id)
            if existing:
                text = existing
            else:
                en_text = (t.detail or "").strip()
                if not en_text:
                    missing_text_count += 1
                    continue

                # Translate EN → target language
                translated = _call_llm_translate_detail(en_text, lang, track_name, artist_name)

                # Language-specific TTS prep
                if lang == "es":
                    translated = prepare_for_tts_es(
                        translated, rank=0,
                        track_name=track_name, artist_name=artist_name,
                        strip_markdown=True, number_normalize=True,
                    )
                elif lang == "pt-BR":
                    translated = prepare_for_tts_pt_br(
                        translated, rank=0,
                        track_name=track_name, artist_name=artist_name,
                        strip_markdown=True, number_normalize=True,
                    )

                # Upsert TrackLocale(detail_text)
                existing_row = db.exec(
                    select(TrackLocale).where(
                        TrackLocale.track_id == t.id,
                        TrackLocale.language_code == lang
                    )
                ).first()
                if existing_row:
                    existing_row.detail_text = translated
                    db.add(existing_row)
                else:
                    db.add(TrackLocale(track_id=t.id, language_code=lang, detail_text=translated))
                localized_by_track_id[t.id] = translated
                text = translated

        items.append({
            "track_id": t.id,
            "spotify_track_id": sid,
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": t.album_name or "TopSpot40 Detail Tracks",
            "detail": text,
            "language": lang,
        })

    # Commit any new/updated TrackLocale rows
    try:
        db.commit()
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Commit failed while saving TrackLocale: {ex}")

    logger.info("🎯 Ready to generate %d (of %d diagnosed) detail TTS files", len(items), len(missing_sids))
    logger.info("🚫 Skipped %d tracks due to missing %s detail text",
                missing_text_count, "EN" if lang == "en" else f"{lang} (and no EN to translate)")

    if not items:
        return {
            "generated": 0,
            "skipped": missing_text_count,
            "missing_found": len(missing_sids_all),
            "files": [],
            "message": "No eligible tracks with detail text to synthesize (or Tracks not found by spotify_track_id).",
        }

    # Per-language voice / model
    voice_cfg = (TTS_PROFILES.get(lang, {}).get("detail") or {})
    voice_id = voice_cfg.get("voice_id") or VOICE_ID_TRACK
    voice_settings = voice_cfg.get("settings") or {}
    model_id = MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))
    logger.debug(
        "🎙️ Detail TTS config | lang=%s | model_id=%s | voice_id=%s | settings=%s | default_lang=%s",
        lang, model_id, voice_id, voice_settings, DEFAULT_TTS_LANGUAGE,
    )

    # Defensive final prep (Spanish/PT-BR) before synth — idempotent
    for it in items:
        if it.get("language") == "es":
            it["detail"] = prepare_for_tts_es(
                it["detail"], rank=0,
                track_name=it["track_name"], artist_name=it["artist_name"],
                strip_markdown=True, number_normalize=True,
            )
        elif it.get("language") == "pt-BR":
            it["detail"] = prepare_for_tts_pt_br(
                it["detail"], rank=0,
                track_name=it["track_name"], artist_name=it["artist_name"],
                strip_markdown=True, number_normalize=True,
            )

    voice_cfg = (TTS_PROFILES.get(lang, {}).get("detail") or {})
    voice_id = voice_cfg.get("voice_id") or VOICE_ID_TRACK
    voice_settings = voice_cfg.get("settings") or {}
    model_id = voice_cfg.get("model_id") or MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))

    return generate_tts_batch(
        items=items,
        text_key="detail",
        voice_id=voice_id,
        voice_settings=voice_settings,
        output_dir=Path("data/mp3_files/track_detail_mp3_files"),
        filename_func=generate_detail_filename,
        log_prefix=f"Track Detail [{lang}]",
        overwrite=overwrite,
        play=play,
        default_language=lang,
        normalize=True,
        model_id=model_id,  # <-- important
    )
