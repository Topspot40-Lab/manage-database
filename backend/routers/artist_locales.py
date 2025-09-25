# backend/routers/artist_locales.py
from fastapi import APIRouter, Depends, Query
from typing import List, Optional, Dict, Any
from pathlib import Path

from sqlmodel import Session, select
from sqlalchemy import exists, and_, or_

from backend.database import get_db
from backend.models.dbmodels import Artist, ArtistLocale
from backend.config import ELEVENLABS_API_KEY
from backend.services.elevenlabs_tts import synth_to_mp3_bytes
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai

router = APIRouter(prefix="/locales/artist")

SUPPORTED_LANGS = ["es", "pt-BR"]

# ---------- local output dir for artist TTS ----------
# LOCAL_ARTIST_MP3_DIR = Path("data/mp3_files/artist_mp3_files")
# LOCAL_ARTIST_MP3_DIR.mkdir(parents=True, exist_ok=True)

# ---------- local output dirs for artist TTS ----------
LOCAL_ARTIST_MP3_DIR_ES    = Path("data/mp3_files/artist_mp3_files_es")
LOCAL_ARTIST_MP3_DIR_PT_BR = Path("data/mp3_files/artist_mp3_files_pt_br")

for _d in (LOCAL_ARTIST_MP3_DIR_ES, LOCAL_ARTIST_MP3_DIR_PT_BR):
    _d.mkdir(parents=True, exist_ok=True)

def _dir_for_lang(lang: str) -> Path:
    l = (lang or "").strip().lower()
    if l == "es":
        return LOCAL_ARTIST_MP3_DIR_ES
    if l.startswith("pt"):
        return LOCAL_ARTIST_MP3_DIR_PT_BR
    # fallback (shouldn’t hit here)
    return LOCAL_ARTIST_MP3_DIR_ES

# ---------- helpers ----------
def _normalize_langs(langs: List[str]) -> List[str]:
    """Keep only supported languages, preserve order, dedupe."""
    out, seen = [], set()
    for l in langs:
        if l in SUPPORTED_LANGS and l not in seen:
            out.append(l)
            seen.add(l)
    return out

def generate_artist_description(lang: str, artist: Artist) -> str:
    """
    Stub you can swap with XAI. Uses EN as seed when present.
    """
    base = (artist.artist_description or "").strip()
    if lang == "es":
        return base or f"{artist.artist_name} es una figura destacada de la música."
    if lang == "pt-BR":
        return base or f"{artist.artist_name} é uma figura de destaque na música."
    return base

def _text_for_tts(artist: Artist, loc: Optional[ArtistLocale]) -> Optional[str]:
    """
    Prefer localized text (artist_locale.artist_description_text) else fallback to EN/base.
    Skip too-short strings to avoid junk TTS.
    """
    txt = (loc.artist_description_text.strip() if loc and loc.artist_description_text else None) \
          or (artist.artist_description.strip() if artist.artist_description else None)
    if txt and len(txt) >= 20:
        return txt
    return None

def pick_artists(
    db: Session,
    artist_ids: Optional[List[int]],
    limit: int,
    offset: int,
    langs: List[str],
    only_missing: bool
) -> List[Artist]:
    """
    When only_missing=True, return artists where at least ONE of the requested langs
    is missing a locale TTS (i.e., no ArtistLocale with that lang and a non-null tts_key).
    """
    q = select(Artist)
    if artist_ids:
        q = q.where(Artist.id.in_(artist_ids))

    if only_missing and langs:
        # For each language, build an EXISTS() that there IS a locale WITH tts for that lang.
        # We want artists where NOT all languages have TTS => at least one lang lacks TTS.
        has_tts_per_lang = [
            exists().where(
                and_(
                    ArtistLocale.artist_id == Artist.id,
                    ArtistLocale.language_code == lang,
                    ArtistLocale.tts_key.isnot(None)
                )
            )
            for lang in langs
        ]
        # Artists where (has_tts for lang1) AND (has_tts for lang2) ... is NOT true.
        # Equivalent: at least one lang is missing TTS.
        # We can express "at least one missing" as: NOT (AND all have TTS) == OR of NOT has_tts(lang_i).
        missing_any = or_(*[~cond for cond in has_tts_per_lang])
        q = q.where(missing_any)

    q = q.order_by(Artist.id.asc()).offset(offset).limit(limit)
    return db.exec(q).all()

# ============================================================
# A) TEXT ONLY — generate / upsert artist descriptions (no audio)
# ============================================================
@router.post("/descriptions", summary="Generate/Upsert artist_locale descriptions in ES/PT-BR (no audio)")
def upsert_artist_descriptions(
    languages: List[str] = Query(["es", "pt-BR"]),
    artist_ids: Optional[List[int]] = Query(None),
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    only_missing_text: bool = Query(False),
    dry_run: bool = Query(True),
    source: str = Query("xai", pattern="^(seed|xai)$"),  # default to xai now
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    langs = _normalize_langs(languages)
    if not langs:
        return {"processed": 0, "note": "No supported languages requested."}

    artists = pick_artists(db, artist_ids, limit, offset, langs, only_missing_text)

    # Language label mapping for your XAI function’s prompt
    lang_label = {
        "es": "Spanish",
        "pt-BR": "Portuguese (Brazil)",
    }

    # Prepare XAI results per language (batch call once per lang)
    xai_descs_by_lang: Dict[str, Dict[str, str]] = {}  # lang -> {name_lower: desc}
    if source == "xai" and artists:
        unique_input = [{"artist_name": a.artist_name} for a in artists if (a.artist_name or "").strip()]
        for lang in langs:
            label = lang_label[lang]
            results = get_artist_descriptions_from_xai(unique_input, label) or []
            # Map name_lower -> description
            xai_descs_by_lang[lang] = {
                (r.get("artist_name", "").strip().lower()): r.get("artist_description", "").strip()
                for r in results
                if r.get("artist_name") and r.get("artist_description")
            }

    planned: List[Dict[str, Any]] = []
    processed = 0
    for artist in artists:
        name_lower = (artist.artist_name or "").strip().lower()
        for lang in langs:
            # If caller wants only locales MISSING text, skip ones that already have text
            if only_missing_text:
                existing = db.exec(
                    select(ArtistLocale)
                    .where(ArtistLocale.artist_id == artist.id)
                    .where(ArtistLocale.language_code == lang)
                ).first()
                if existing and (existing.artist_description_text or "").strip():
                    continue

            # Pick text source: XAI if available, else fallback stub
            text = xai_descs_by_lang.get(lang, {}).get(name_lower) if source == "xai" else None
            if not text:
                text = generate_artist_description(lang, artist)

            planned.append({
                "artist_id": artist.id,
                "artist": artist.artist_name,
                "language": lang,
                "will_write": {"artist_description_text": True},
                "source": "xai" if source == "xai" else "seed",
            })
            if dry_run:
                continue

            loc = db.exec(
                select(ArtistLocale)
                .where(ArtistLocale.artist_id == artist.id)
                .where(ArtistLocale.language_code == lang)
            ).first()

            if loc:
                loc.artist_description_text = text
            else:
                loc = ArtistLocale(
                    artist_id=artist.id,
                    language_code=lang,
                    artist_description_text=text,
                )
                db.add(loc)

            db.commit()
            processed += 1
    return {
        "processed": processed if not dry_run else len(planned),
        "dry_run": dry_run,
        "languages": langs,
        "offset": offset,
        "sample_planned_actions": planned[:10],
        "note": "(dry-run) no DB writes performed" if dry_run else "artist descriptions upserted",
    }

# ============================================================
# B) AUDIO ONLY — synth & SAVE LOCALLY (no upload here)
# ============================================================
@router.post("/tts", summary="Synthesize/save artist MP3s for ES/PT-BR from existing text (local review)")
def synth_artist_tts(
    languages: List[str] = Query(["es", "pt-BR"]),
    artist_ids: Optional[List[int]] = Query(None),
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    overwrite: bool = Query(False, description="If false, skip locales with existing tts_key"),
    only_missing_tts: bool = Query(False, description="Only artists missing TTS for any requested language"),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    langs = _normalize_langs(languages)
    if not langs:
        return {"processed": 0, "note": "No supported languages requested."}

    artists = pick_artists(db, artist_ids, limit, offset, langs, only_missing_tts)

    planned: List[Dict[str, Any]] = []
    tts_errors: List[str] = []
    processed = 0
    skipped_existing = 0
    skipped_no_text = 0

    for artist in artists:
        # Filename based on Spotify artist id; fallback to DB numeric id
        spotify_id = getattr(artist, "spotify_artist_id", None)
        file_key = f"{spotify_id}.mp3" if (spotify_id and str(spotify_id).strip()) else f"{artist.id}.mp3"

        for lang in langs:
            # resolve locale row and source text
            loc = db.exec(
                select(ArtistLocale)
                .where(ArtistLocale.artist_id == artist.id)
                .where(ArtistLocale.language_code == lang)
            ).first()
            already_has_tts = bool(loc and loc.tts_key)
            text = _text_for_tts(artist, loc)

            # choose per-language local dir and full path (define BEFORE planned.append)
            local_dir = _dir_for_lang(lang)
            local_path = (local_dir / file_key)

            planned.append({
                "artist_id": artist.id,
                "artist": artist.artist_name,
                "language": lang,
                "text_source": "locale" if (loc and loc.artist_description_text) else "english_fallback",
                "key": file_key,
                "local_path": local_path.as_posix(),   # portable path for logs/DB
                "will_synth": bool(text),
                "already_has_tts": already_has_tts,
            })

            # Single gate: prevents ANY synth when dry_run is True
            should_synth = (not dry_run) and (overwrite or not already_has_tts) and bool(text)

            if not should_synth:
                if not text:
                    skipped_no_text += 1
                elif already_has_tts and not overwrite:
                    skipped_existing += 1
                continue

            # --- TTS
            try:
                mp3 = synth_to_mp3_bytes(
                    text=text,
                    lang=lang,
                    kind="artist",
                    api_key=ELEVENLABS_API_KEY or "",
                    retries=1,
                    # log_when_disabled=False  # if your helper supports it
                )

            except Exception as e:
                tts_errors.append(f"artist_id={artist.id} lang={lang}: exception {e}")
                continue

            if not mp3:
                tts_errors.append(f"artist_id={artist.id} lang={lang}: no audio (disabled or error)")
                continue

            # --- Save locally for review
            try:
                local_dir.mkdir(parents=True, exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(mp3)
            except Exception as e:
                tts_errors.append(f"artist_id={artist.id} lang={lang}: failed to write {local_path} ({e})")
                continue

            # --- Upsert locale pointers: record local path
            if not loc:
                loc = ArtistLocale(
                    artist_id=artist.id,
                    language_code=lang,
                    artist_description_text=text,  # if EN fallback used, we store it
                    tts_bucket="local",
                    tts_key=local_path.as_posix(),
                )
                db.add(loc)
            else:
                loc.tts_bucket = "local"
                loc.tts_key = local_path.as_posix()
                if not loc.artist_description_text:
                    loc.artist_description_text = text

            processed += 1

    if not dry_run:
        db.commit()

    return {
        "languages": langs,
        "offset": offset,
        "count_in_batch": len(artists),
        "processed": processed if not dry_run else len(planned),
        "skipped_existing": skipped_existing,
        "skipped_no_text": skipped_no_text,
        "dry_run": dry_run,
        "sample_planned_actions": planned[:10],
        "tts_errors": tts_errors,
        "note": "(dry-run) no files written" if dry_run else "artist TTS synthesized and saved locally",
    }
