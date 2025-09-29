from __future__ import annotations

import logging
import time
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from backend.database import get_db
from backend.models.collection_models import Collection
from backend.models.dbmodels import CollectionTrackRanking, Track, Artist
from backend.models.dbmodels import Track, Artist
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
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.tts_prep import prepare_for_tts_es, prepare_for_tts_pt_br
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger(__name__)  # resolves to "backend.routers.tts_collection_intro"

collection_intro_router = APIRouter(prefix="/tts/collection-intro")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_count_to_limit(count_param: Optional[int]) -> Optional[int]:
    """
    None or <0 => unlimited (None); 0 => 0; >0 => that number
    """
    try:
        raw = int(count_param) if count_param is not None else -1
    except (TypeError, ValueError):
        raw = -1
    return None if raw < 0 else raw


def generate_collection_intro_filename(slug: str, rank: int) -> str:
    """
    Local filename: <slug>_<rank:02>.mp3  (no 'collection_intro/' prefix)
    """
    return f"{normalize_for_filename(slug)}_{int(rank):02}.mp3"


_LANG_LABEL = {
    "en": "English",
    "es": "Spanish",
    "pt-BR": "Portuguese (Brazil)",
}

def _call_llm_translate_intro(en_text: str, lang: str, track_name: str, artist_name: str, rank: int | None, collection_name: str | None) -> str:
    api_key = (XAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Missing XAI_API_KEY env var")

    target_label = _LANG_LABEL.get(lang, lang)
    rank_phrase = f"(rank {rank})" if rank else ""
    coll_phrase = f"in the “{collection_name}” collection" if collection_name else "in this collection"
    system = f"Translate an English radio-style song intro to {target_label}. Keep the announcer tone, concise, punchy. Keep facts identical."
    user = f"""English intro {rank_phrase} {coll_phrase}:
{en_text}

Constraints:
- Keep EXACT song/artist spellings as provided: {track_name} — {artist_name}.
- Maintain the *collection context* implied by the line (do not remove it).
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

@collection_intro_router.post("/by-collection/{slug}")
def generate_collection_intro_tts(
    slug: str,
    count: int = Query(
        -1, description="Number of collection-intro TTS files to generate. Use -1 for all ranks."
    ),
    overwrite: bool = Query(False),
    only_missing: bool = Query(True, description="Skip ranks that already have an MP3 unless overwrite=true"),
    play: bool = Query(False),
        language: str = Query(
            "en",
            pattern=r"^(en|es|pt-BR|ptbr|pt-br)$",
            description="Target language for TTS (en|es|pt-BR)",
        )
        ,
    start_rank: Optional[int] = Query(None, description="Optional lower bound for rank"),
    end_rank: Optional[int] = Query(None, description="Optional upper bound for rank"),
    db: Session = Depends(get_db),
):
    """
    Generate *collection* intro MP3s to local disk for ranks in a given collection.

    - Filenames: `<slug>_<rank:02>.mp3`
    - Output dir: `data/mp3_files/collection_intro_mp3_files`
    - If `language != en`, intro text is translated EN→target, with language-specific TTS prep.
    - Uses `CollectionTrackRanking.intro` if present (English). Otherwise a concise default is synthesized.
    - This endpoint does **not** upload; your uploader should route to `audio-<lang>/collection_intro/`.
    """

    # normalize language key (defensive)
    lang = "pt-BR" if language.lower() in ("ptbr", "pt-br") else language
    limit = _parse_count_to_limit(count)

    coll = db.exec(
        select(Collection).where(Collection.slug == slug)
    ).first()
    if not coll:
        raise HTTPException(status_code=404, detail=f"Collection not found: {slug}")

    # Load ranking rows with track/artist eager-loaded
    rows = db.exec(
        select(CollectionTrackRanking)
        .where(CollectionTrackRanking.collection_id == coll.id)
        .order_by(CollectionTrackRanking.ranking)
        .options(
            selectinload(CollectionTrackRanking.track).selectinload(Track.artist)
        )
    ).all()
    if not rows:
        return {"generated": 0, "skipped": 0, "missing_found": 0, "files": [], "message": "No rankings in this collection."}

    # Per-language voice / model / settings (reuse "intro" voice profile)
    voice_cfg = (TTS_PROFILES.get(lang, {}).get("intro") or {})
    voice_id = voice_cfg.get("voice_id") or VOICE_ID_INTRO
    voice_settings = voice_cfg.get("settings") or {}
    model_id = voice_cfg.get("model_id") or MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))
    if model_id is None:
        return {
            "generated": 0, "skipped": 0, "missing_found": 0, "files": [],
            "error": f"MODEL_BY_LANG has no entry for '{lang}' nor default '{DEFAULT_TTS_LANGUAGE}'"
        }

    out_dir = Path("data/mp3_files/collection_intro_mp3_files")
    out_dir.mkdir(parents=True, exist_ok=True)

    items: List[Dict[str, Any]] = []
    skipped = 0
    considered = 0

    # rank range filter
    def _in_range(rk: int) -> bool:
        if start_rank is not None and rk < start_rank:
            return False
        if end_rank is not None and rk > end_rank:
            return False
        return True

    for r in rows:
        rk = int(r.ranking or 0)
        if not _in_range(rk):
            continue

        basename = generate_collection_intro_filename(slug, rk)
        fpath = out_dir / basename

        if fpath.exists() and only_missing and not overwrite:
            skipped += 1
            continue

        track: Track = r.track
        artist: Optional[Artist] = track.artist if track else None
        track_name = (track.track_name or "") if track else ""
        artist_name = (artist.artist_name or "Unknown Artist") if artist else "Unknown Artist"

        # Base EN text: prefer row.intro (if stored via importer); else a concise default with collection context
        en_text = (getattr(r, "intro", None) or "").strip()
        if not en_text:
            en_text = f"At number {rk}, from the {coll.name} collection: '{track_name}' by {artist_name}."

        # Translate if needed
        if lang == "en":
            text = en_text
        else:
            translated = _call_llm_translate_intro(en_text, lang, track_name, artist_name, rk, coll.name)
            if lang == "es":
                translated = prepare_for_tts_es(
                    translated,
                    rank=rk,
                    track_name=track_name,
                    artist_name=artist_name,
                    strip_markdown=True,
                    number_normalize=True,
                )
            elif lang == "pt-BR":
                translated = prepare_for_tts_pt_br(
                    translated,
                    rank=rk,
                    track_name=track_name,
                    artist_name=artist_name,
                    strip_markdown=True,
                    number_normalize=True,
                )
            text = translated

        # Defensive per-language prep (idempotent)
        if lang == "es":
            text = prepare_for_tts_es(
                text,
                rank=rk,
                track_name=track_name,
                artist_name=artist_name,
                strip_markdown=True,
                number_normalize=True,
            )
        elif lang == "pt-BR":
            text = prepare_for_tts_pt_br(
                text,
                rank=rk,
                track_name=track_name,
                artist_name=artist_name,
                strip_markdown=True,
                number_normalize=True,
            )

        items.append(
            {
                "track_id": track.id if track else None,
                "track_name": track_name,
                "artist_name": artist_name,
                "album_name": coll.name or "TopSpot Collection Intros",
                "intro": text,        # <-- text key used below
                "rank": rk,
                "collection_slug": slug,
                "collection_name": coll.name,
                "language": lang,
            }
        )

        considered += 1
        if limit is not None and len(items) >= limit:
            break

    if not items:
        return {
            "generated": 0,
            "skipped": skipped or considered,
            "missing_found": considered,
            "files": [],
            "message": "No eligible ranks to synthesize (existing files and/or filters).",
        }

    # Generate to local disk. Your uploader should route items to audio-<lang>/collection_intro/.
    return generate_tts_batch(
        items=items,
        text_key="intro",
        voice_id=voice_id,
        voice_settings=voice_settings,
        output_dir=out_dir,
        filename_func=lambda it: generate_collection_intro_filename(it["collection_slug"], int(it["rank"])),
        log_prefix=f"Collection Intro [{lang}]",
        overwrite=overwrite,
        play=play,
        default_language=lang,
        normalize=True,
        model_id=model_id,
    )
