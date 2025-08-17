# backend/routers/artist_locales.py
from fastapi import APIRouter, Depends, Query
from typing import List, Optional, Dict, Any
from sqlmodel import Session, select

from backend.database import get_db
from backend.models.dbmodels import Artist, ArtistLocale
from backend.config import ELEVENLABS_API_KEY, ELEVEN_MODEL_ID
from backend.utils.storage_keys import bucket_for
from backend.services.supabase_storage import upload_bytes
from backend.services.elevenlabs_tts import synth_to_mp3_bytes

router = APIRouter(prefix="/locales/artist", tags=["artist-locales"])

SUPPORTED_LANGS = ["es", "pt-BR"]

# ---------- helpers ----------
def slugify(s: str) -> str:
    import re
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_") or "artist"

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

def pick_artists(db: Session, artist_ids: Optional[List[int]], limit: int, offset: int,
                 langs: List[str], only_missing: bool) -> List[Artist]:
    if artist_ids:
        return db.exec(select(Artist).where(Artist.id.in_(artist_ids)).offset(offset).limit(limit)).all()
    if not only_missing:
        return db.exec(select(Artist).order_by(Artist.id.asc()).offset(offset).limit(limit)).all()
    # Only artists missing at least one requested locale row
    sub = (
        select(ArtistLocale.artist_id)
        .where(ArtistLocale.artist_id == Artist.id)
        .where(ArtistLocale.language_code.in_(langs))
    )
    # “missing” = NOT EXISTS any locale for at least one requested language
    q = select(Artist).where(~sub.exists()).order_by(Artist.id.asc()).offset(offset).limit(limit)
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
    only_missing_text: bool = Query(False, description="If true, only artists missing ANY of the requested locales"),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    langs = [l for l in languages if l in SUPPORTED_LANGS]
    langs = list(dict.fromkeys(langs))
    if not langs:
        return {"processed": 0, "note": "No supported languages requested."}

    artists = pick_artists(db, artist_ids, limit, offset, langs, only_missing_text)
    planned, processed = [], 0

    for artist in artists:
        for lang in langs:
            text = generate_artist_description(lang, artist)

            planned.append({
                "artist_id": artist.id,
                "artist": artist.artist_name,
                "language": lang,
                "will_write": {"artist_description_text": True},
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
# B) AUDIO ONLY — synth / upload MP3s (no text generation)
# ============================================================
@router.post("/tts", summary="Synthesize/upload artist MP3s for ES/PT-BR from existing text")
def synth_artist_tts(
    languages: List[str] = Query(["es", "pt-BR"]),
    artist_ids: Optional[List[int]] = Query(None),
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    overwrite: bool = Query(False, description="If false, skip locales with existing tts_key"),
    only_missing_tts: bool = Query(False, description="Only locales missing tts_key"),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    langs = [l for l in languages if l in SUPPORTED_LANGS]
    langs = list(dict.fromkeys(langs))
    if not langs:
        return {"processed": 0, "note": "No supported languages requested."}

    artists = pick_artists(db, artist_ids, limit, offset, langs, only_missing=False)
    planned, tts_errors, processed = [], [], 0

    for artist in artists:
        artist_slug = slugify(artist.artist_name or f"artist_{artist.id}")
        for lang in langs:
            loc = db.exec(
                select(ArtistLocale)
                .where(ArtistLocale.artist_id == artist.id)
                .where(ArtistLocale.language_code == lang)
            ).first()

            # text source: locale first, else EN base
            text = (loc.artist_description_text if loc and loc.artist_description_text else None) \
                   or (artist.artist_description or "").strip()

            bucket = bucket_for("artist", lang)          # e.g., artist-mp3-files-es / -ptbr
            key    = f"{artist_slug}.mp3"

            already_has_tts = bool(loc and loc.tts_key)
            if only_missing_tts and already_has_tts:
                continue
            if (not overwrite) and already_has_tts:
                # skip if we already have audio and overwrite is false
                continue

            planned.append({
                "artist_id": artist.id,
                "artist": artist.artist_name,
                "language": lang,
                "text_source": "locale" if loc and loc.artist_description_text else "english_fallback",
                "bucket": bucket,
                "key": key,
                "will_synth": bool(text),
            })

            if dry_run:
                continue

            if not text:
                tts_errors.append(f"artist_id={artist.id} lang={lang}: no text to synth")
                continue

            mp3 = synth_to_mp3_bytes(
                text=text,
                lang=lang,
                kind="artist",
                api_key=ELEVENLABS_API_KEY or "",
                model_id=ELEVEN_MODEL_ID,
                retries=1,
            )
            if not mp3:
                tts_errors.append(f"artist_id={artist.id} lang={lang}: no audio")
                continue

            upload_bytes(bucket=bucket, key=key, data=mp3)

            # upsert/set tts pointers
            if not loc:
                loc = ArtistLocale(
                    artist_id=artist.id,
                    language_code=lang,
                    artist_description_text=text,  # keep text in sync if it was EN fallback
                    tts_bucket=bucket,
                    tts_key=key,
                )
                db.add(loc)
            else:
                loc.tts_bucket = bucket
                loc.tts_key = key
                if not loc.artist_description_text:
                    loc.artist_description_text = text  # backfill if using EN fallback

            db.commit()
            processed += 1

    return {
        "processed": processed if not dry_run else len(planned),
        "dry_run": dry_run,
        "languages": langs,
        "offset": offset,
        "sample_planned_actions": planned[:10],
        "tts_errors": tts_errors,
        "note": "(dry-run) no uploads performed" if dry_run else "artist TTS synthesized/uploaded",
    }
