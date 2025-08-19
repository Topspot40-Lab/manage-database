from fastapi import APIRouter, Depends, Query
from typing import List, Optional, Dict, Any
from sqlmodel import Session, select

from backend.database import get_db
from backend.models.dbmodels import (
    Track, TrackLocale, Artist, TrackRanking, DecadeGenre, Genre, Decade
)
from backend.config import ELEVENLABS_API_KEY, ELEVEN_MODEL_ID
from backend.utils.storage_keys import bucket_for, key_for
from backend.services.supabase_storage import upload_bytes
from backend.services.elevenlabs_tts import synth_to_mp3_bytes

# Optional XAI batch generator
try:
    from backend.services.xai_track_detail import get_track_details_from_xai
    HAS_XAI_TRACK = True
except Exception:
    HAS_XAI_TRACK = False

router = APIRouter(prefix="/locales/track-detail", tags=["track-detail-locales"])
SUPPORTED_LANGS = ["es", "pt-BR"]

# ----------------- helpers -----------------
def generate_track_detail_seed(lang: str, track: Track, artist_name: str) -> str:
    base = (track.detail or "").strip()
    if lang == "es":
        return base or f"{artist_name} presenta «{track.track_name}», un tema destacado en su trayectoria."
    if lang == "pt-BR":
        return base or f"{artist_name} apresenta “{track.track_name}”, uma faixa marcante na sua carreira."
    return base or f"{artist_name} - {track.track_name}"

def compute_detail_key(db: Session, track_id: int) -> str:
    """
    Prefer a rank-based filename like '1960s_country_01.mp3' using the
    best/lowest ranking for this track. If none, fallback to track_{id}.mp3
    """
    row = db.exec(
        select(Decade.decade_name, Genre.genre_name, TrackRanking.ranking)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .join(Decade, Decade.id == DecadeGenre.decade_id)
        .join(Genre, Genre.id == DecadeGenre.genre_id)
        .where(TrackRanking.track_id == track_id)
        .order_by(TrackRanking.ranking.asc())
        .limit(1)
    ).first()
    if row:
        decade, genre, rank = row
        return key_for(decade, genre, rank)
    return f"track_{track_id:06d}.mp3"

def pick_tracks(db: Session, track_ids: Optional[List[int]], limit: int, offset: int) -> List[Track]:
    if track_ids:
        return db.exec(select(Track).where(Track.id.in_(track_ids)).offset(offset).limit(limit)).all()
    return db.exec(select(Track).order_by(Track.id.asc()).offset(offset).limit(limit)).all()

def load_artist_name(db: Session, track: Track) -> str:
    if getattr(track, "artist", None) and track.artist and track.artist.artist_name:
        return track.artist.artist_name
    a = db.exec(select(Artist.artist_name).where(Artist.id == track.artist_id)).first()
    return a or "Unknown Artist"

# ============================================================
# A) TEXT ONLY — generate / upsert detail_text (no audio)
# ============================================================
@router.post("/details", summary="Generate/Upsert track_locale.detail_text in ES/PT-BR (no audio)")
def upsert_track_details(
    languages: List[str] = Query(["es", "pt-BR"]),
    track_ids: Optional[List[int]] = Query(None),
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    only_missing_text: bool = Query(False, description="Skip languages that already have detail_text"),
    dry_run: bool = Query(True),
    source: str = Query("seed", pattern="^(seed|xai)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    langs = [l for l in languages if l in SUPPORTED_LANGS]
    langs = list(dict.fromkeys(langs))
    if not langs:
        return {"processed": 0, "note": "No supported languages requested."}

    tracks = pick_tracks(db, track_ids, limit, offset)
    planned, processed = [], 0

    xai_by_lang: Dict[str, Dict[tuple, str]] = {}  # lang -> {(track, artist): text}
    if source == "xai" and HAS_XAI_TRACK and tracks:
        items = []
        for t in tracks:
            artist_name = load_artist_name(db, t)
            items.append({
                "track_name": (t.track_name or "").strip(),
                "artist_name": (artist_name or "").strip(),
                "year_released": t.year_released,
            })
        for lang in langs:
            label = "Spanish" if lang == "es" else "Portuguese (Brazil)"
            results = get_track_details_from_xai(items, label) or []
            xai_by_lang[lang] = {
                ((r.get("track_name","").strip().lower(), r.get("artist_name","").strip().lower())):
                r.get("detail_text","").strip()
                for r in results if r.get("track_name") and r.get("artist_name") and r.get("detail_text")
            }

    for t in tracks:
        artist_name = load_artist_name(db, t)
        for lang in langs:
            loc = db.exec(
                select(TrackLocale)
                .where(TrackLocale.track_id == t.id)
                .where(TrackLocale.language_code == lang)
            ).first()

            if only_missing_text and loc and (loc.detail_text or "").strip():
                planned.append({
                    "track_id": t.id, "track": t.track_name, "language": lang,
                    "skipped": True, "reason": "already has detail_text"
                })
                continue

            text = None
            if source == "xai" and HAS_XAI_TRACK:
                key = ((t.track_name or "").strip().lower(), artist_name.strip().lower())
                text = xai_by_lang.get(lang, {}).get(key)
            if not text:
                text = generate_track_detail_seed(lang, t, artist_name)

            planned.append({
                "track_id": t.id,
                "track": t.track_name,
                "artist": artist_name,
                "language": lang,
                "will_write": {"detail_text": True},
                "source": source if (source == "xai" and HAS_XAI_TRACK) else "seed",
            })

            if dry_run:
                continue

            if loc:
                loc.detail_text = text
            else:
                loc = TrackLocale(
                    track_id=t.id,
                    language_code=lang,
                    detail_text=text,
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
        "note": "(dry-run) no DB writes performed" if dry_run else "track detail locales upserted",
    }

# ============================================================
# B) AUDIO ONLY — synth / upload detail MP3s (no text generation)
# ============================================================
@router.post("/tts", summary="Synthesize/upload detail MP3s for ES/PT-BR from existing text")
def synth_track_detail_tts(
    languages: List[str] = Query(["es", "pt-BR"]),
    track_ids: Optional[List[int]] = Query(None),
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

    tracks = pick_tracks(db, track_ids, limit, offset)
    planned, tts_errors, processed = [], [], 0

    for t in tracks:
        artist_name = load_artist_name(db, t)
        for lang in langs:
            loc = db.exec(
                select(TrackLocale)
                .where(TrackLocale.track_id == t.id)
                .where(TrackLocale.language_code == lang)
            ).first()

            text = (loc.detail_text if loc and loc.detail_text else None) or (t.detail or "").strip()
            bucket = bucket_for("detail", lang)
            key    = compute_detail_key(db, t.id)

            already_has_tts = bool(loc and loc.tts_key)
            if only_missing_tts and already_has_tts:
                continue
            if (not overwrite) and already_has_tts:
                continue

            planned.append({
                "track_id": t.id,
                "track": t.track_name,
                "artist": artist_name,
                "language": lang,
                "text_source": "locale" if (loc and loc.detail_text) else "english_fallback",
                "bucket": bucket,
                "key": key,
                "will_synth": bool(text),
            })

            if dry_run:
                continue

            if not text:
                tts_errors.append(f"track_id={t.id} lang={lang}: no text to synth")
                continue

            mp3 = synth_to_mp3_bytes(
                text=text,
                lang=lang,
                kind="detail",
                api_key=ELEVENLABS_API_KEY or "",
                model_id=ELEVEN_MODEL_ID,
                retries=1,
            )
            if not mp3:
                tts_errors.append(f"track_id={t.id} lang={lang}: no audio")
                continue

            upload_bytes(bucket=bucket, key=key, data=mp3)

            if not loc:
                loc = TrackLocale(
                    track_id=t.id, language_code=lang, detail_text=text,
                    tts_bucket=bucket, tts_key=key
                )
                db.add(loc)
            else:
                loc.tts_bucket = bucket
                loc.tts_key = key
                if not loc.detail_text:
                    loc.detail_text = text

            db.commit()
            processed += 1

    return {
        "processed": processed if not dry_run else len(planned),
        "dry_run": dry_run,
        "languages": langs,
        "offset": offset,
        "sample_planned_actions": planned[:10],
        "tts_errors": tts_errors,
        "note": "(dry-run) no uploads performed" if dry_run else "track detail TTS synthesized/uploaded",
    }
