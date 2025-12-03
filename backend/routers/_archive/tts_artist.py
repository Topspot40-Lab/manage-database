# backend/routers/tts_artist.py

from __future__ import annotations

from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from sqlalchemy import and_
from sqlalchemy.orm import selectinload
from pathlib import Path
from typing import List, Dict, Any, Literal
import logging

from backend.database import get_db
from backend.models.dbmodels import Artist
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch
from backend.services.tts_prep import prepare_for_tts_es, prepare_for_tts_pt_br
from backend.config import (
    VOICE_ID_ARTIST,
    TTS_PROFILES,
    MODEL_BY_LANG,
    DEFAULT_TTS_LANGUAGE,
)

logger = logging.getLogger("tts_logger")


artist_router = APIRouter(tags=["Narration"], prefix="/narration")


# Central output directory for all artist MP3s
ARTIST_MP3_DIR = Path("data/mp3_files/artist_mp3_files")
ARTIST_MP3_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
import re

# Remove emoji, ZWJ, variation selectors (keeps plain ASCII clean for TTS)
_EMOJI = re.compile(r"[\u200D\uFE0F\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]+")

def _de_emoji(s: str | None) -> str:
    return _EMOJI.sub("", s or "").strip()

def _get(obj, field: str, default=None):
    """Safe attr-or-key access for ORM/Pydantic rows or dicts."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)



def _canon_lang(language: str) -> str:
    if not language:
        return DEFAULT_TTS_LANGUAGE
    l = language.strip().lower()
    if l in ("ptbr", "pt-br"):
        return "pt-BR"
    if l in ("es", "en"):
        return l
    return language  # pass-through for unexpected but supported keys

def _generate_artist_filename(item: Dict[str, Any]) -> str:
    return f"{item['spotify_artist_id']}.mp3"

# ─────────────────────────────────────────────────────────────────────────────
# GET /tts/artist/list
# ─────────────────────────────────────────────────────────────────────────────
@artist_router.get("/list")
def list_unique_artists(db: Session = Depends(get_db)):
    """
    Returns a numbered list of unique artists from the Artist table
    who have a non-empty description.
    """
    logger.debug("🎨 Fetching all artists with descriptions from database...")

    results: List[Artist] = db.exec(
        select(Artist).where(
            and_(
                Artist.__table__.c.artist_description.is_not(None),
                Artist.__table__.c.artist_description != ""
            )
        ).options(selectinload(Artist.tracks))  # harmless; may help in other contexts
    ).all()

    artists = []
    for index, artist in enumerate(results, start=1):
        mp3_path = ARTIST_MP3_DIR / f"{artist.spotify_artist_id}.mp3"
        artists.append({
            "index": index,
            "artist_id": artist.spotify_artist_id,
            "artist_name": artist.artist_name,
            "artist_description": artist.artist_description,
            "has_description": True,
            "has_mp3": mp3_path.exists(),
        })

        logger.debug(
            f"{index:02d}. 🎤 {artist.artist_name} "
            f"(ID: {artist.spotify_artist_id}) | "
            f"MP3: {'✅' if mp3_path.exists() else '❌'}"
        )

    logger.info(f"🔍 Found {len(artists)} artists with descriptions.")
    return {"total": len(artists), "artists": artists}

# ─────────────────────────────────────────────────────────────────────────────
# POST /tts/artist/by-range
# ─────────────────────────────────────────────────────────────────────────────
@artist_router.post("/by-range")
def generate_artist_tts_range(
    start: int = Query(..., ge=1, description="Start index (1-based) of artist list"),
    end: int = Query(..., ge=1, description="End index (inclusive) of artist list"),
    overwrite: bool = Query(False, description="Overwrite existing MP3 files"),
    play: bool = Query(False, description="Play audio after generation"),
    language: Literal["en", "es", "pt-BR", "ptbr", "pt-br"] = Query("en", description="TTS language (en|es|pt-BR)"),
    db: Session = Depends(get_db)
):
    """
    Generate artist TTS MP3 files for a specified range of artists (by index).
    """
    lang = _canon_lang(language)
    logger.debug(f"🎙️ TTS (Artist) requested for {start}-{end} | overwrite={overwrite}, play={play}, lang={lang}")

    if start > end:
        logger.warning("❌ Invalid range: start > end")
        return {"error": "Start index must be less than or equal to end index."}

    unique_artists = list_unique_artists(db)["artists"]
    selected = unique_artists[start - 1:end]

    # Filter out artists that already have MP3s, unless overwrite=True
    if not overwrite:
        selected = [
            a for a in selected
            if not (ARTIST_MP3_DIR / f"{a['artist_id']}.mp3").exists()
        ]

    items: List[Dict[str, Any]] = []
    for a in selected:
        desc = (a.get("artist_description") or "").strip()
        if not desc:
            continue

        # Defensive language-specific prep (mirrors intro/detail flow)
        if lang == "es":
            desc = prepare_for_tts_es(
                desc, rank=0,
                track_name="", artist_name=a["artist_name"],
                strip_markdown=True, number_normalize=True,
            )
        elif lang == "pt-BR":
            desc = prepare_for_tts_pt_br(
                desc, rank=0,
                track_name="", artist_name=a["artist_name"],
                strip_markdown=True, number_normalize=True,
            )

        desc = _de_emoji(desc)

        items.append({
            "spotify_artist_id": a["artist_id"],
            "artist_name": a["artist_name"],
            "artist_description": desc,
            "language": lang,
        })

    voice_cfg = (TTS_PROFILES.get(lang, {}).get("artist") or {})
    voice_id = voice_cfg.get("voice_id") or VOICE_ID_ARTIST
    voice_settings = voice_cfg.get("settings") or {}
    model_id = MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))

    logger.debug(
        "🎙️ Artist TTS config | lang=%s | model_id=%s | voice_id=%s | settings=%s | items=%d",
        lang, model_id, voice_id, voice_settings, len(items),
    )

    if not items:
        return {"message": "No eligible artists to synthesize.", "files": [], "generated": 0}

    return generate_tts_batch(
        items=items,
        text_key="artist_description",
        voice_id=voice_id,
        voice_settings=voice_settings,
        output_dir=ARTIST_MP3_DIR,
        filename_func=_generate_artist_filename,
        log_prefix=f"Artist [{lang}]",
        overwrite=overwrite,
        play=play,
        default_language=lang,
        normalize=True,
        # model_id=model_id,  # enable if your batch supports it
    )

# ─────────────────────────────────────────────────────────────────────────────
# POST /tts/artist/by-missing
# ─────────────────────────────────────────────────────────────────────────────
@artist_router.post("/by-missing")
async def generate_missing_artist_tts(
    count: int = Query(-1, description="Number of missing artist TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    language: Literal["en", "es", "pt-BR", "ptbr", "pt-br"] = Query("en", description="TTS language (en|es|pt-BR)"),
    db: Session = Depends(get_db)
):
    lang = _canon_lang(language)
    logger.info(f"🧠 Generating up to {count} missing artist TTS files | lang={lang}")

    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=False,
        check_detail_mp3=False,
        check_artist_mp3=True,
        language=lang,
    )
    missing_artists = diagnostics.get("missing_mp3", {}).get("artist_mp3", []) or []

    if count > 0:
        missing_artists = missing_artists[:count]
    items: List[Dict[str, Any]] = []
    for artist in missing_artists:
        # attr-or-dict safe access
        artist_id = _get(artist, "spotify_artist_id")
        artist_name = _get(artist, "artist_name") or _get(artist, "name")
        artist_desc = _get(artist, "artist_description")

        if not artist_id or not artist_name:
            continue

        desc = (artist_desc or "").strip()
        if not desc:
            continue

        # Language-specific normalization (once)
        if lang == "es":
            desc = prepare_for_tts_es(
                desc, rank=0, track_name="", artist_name=artist_name,
                strip_markdown=True, number_normalize=True,
            )
        elif lang == "pt-BR":
            desc = prepare_for_tts_pt_br(
                desc, rank=0, track_name="", artist_name=artist_name,
                strip_markdown=True, number_normalize=True,
            )

        desc = _de_emoji(desc)  # prevent emojibake

        items.append({
            "spotify_artist_id": artist_id,
            "artist_name": artist_name,
            "artist_description": desc,
            "language": lang,
        })

        if 0 < count <= len(items):
            break

    logger.info(f"🎯 Ready to generate {len(items)} artist TTS files")

    voice_cfg = (TTS_PROFILES.get(lang, {}).get("artist") or {})
    voice_id = voice_cfg.get("voice_id") or VOICE_ID_ARTIST
    voice_settings = voice_cfg.get("settings") or {}
    model_id = MODEL_BY_LANG.get(lang, MODEL_BY_LANG.get(DEFAULT_TTS_LANGUAGE))

    logger.debug(
        "🎙️ Artist TTS config | lang=%s | model_id=%s | voice_id=%s | settings=%s",
        lang, model_id, voice_id, voice_settings,
    )

    if not items:
        return {"message": "No eligible artists to synthesize.", "files": [], "generated": 0}

    return generate_tts_batch(
        items=items,
        text_key="artist_description",
        voice_id=voice_id,
        voice_settings=voice_settings,
        output_dir=ARTIST_MP3_DIR,
        filename_func=_generate_artist_filename,
        log_prefix=f"Artist [{lang}]",
        overwrite=overwrite,
        play=play,
        default_language=lang,
        normalize=True,
        model_id=model_id,  # enable if your batch supports it
    )
