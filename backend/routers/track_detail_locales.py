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
import logging
logger = logging.getLogger("track_detail_locales")

# Optional XAI batch generator
try:
    from backend.services.xai_track_detail import get_track_details_from_xai
    HAS_XAI_TRACK = True
except Exception:
    HAS_XAI_TRACK = False

router = APIRouter(prefix="/locales/track-detail", tags=["track-detail-locales"])
SUPPORTED_LANGS = ["es", "pt-BR"]

import unicodedata
import re as _re

def _norm_key(name: str) -> str:
    """
    Normalize for fuzzy-ish equality:
    - lowercase
    - strip/condense whitespace
    - strip quotes and common punctuation
    - fold accents (NFKD)
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    # unify quotes/emdash/etc. and remove most punctuation except & and +
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = _re.sub(r"[^\w\s&+]", " ", s)   # keep & and + (common in artist names)
    s = _re.sub(r"\s+", " ", s).strip()
    return s



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
        return db.exec(
            select(Track)
            .where(Track.id.in_(track_ids))
            .order_by(Track.id.asc())
            .offset(offset).limit(limit)
        ).all()
    return db.exec(
        select(Track).order_by(Track.id.asc())
        .offset(offset).limit(limit)
    ).all()

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
    # allow_fallback: bool = Query(True, description="If false: do not seed when XAI text is missing"),

    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    langs = [l for l in languages if l in SUPPORTED_LANGS]
    langs = list(dict.fromkeys(langs))
    if not langs:
        return {"processed": 0, "note": "No supported languages requested."}

    tracks = pick_tracks(db, track_ids, limit, offset)
    requested_offset = offset
    logger.info(
        "📝 Upserting detail_text | langs=%s | limit=%s offset=%s dry_run=%s source=%s",
        langs, limit, requested_offset, dry_run, source
    )

    logger.debug("Picked %d tracks (ids: %s...)", len(tracks), [t.id for t in tracks[:5]])

    planned, processed = [], 0


    if source == "xai" and HAS_XAI_TRACK and tracks:
        items = []
        for t in tracks:
            artist_name = load_artist_name(db, t)
            items.append({
                "track_id": t.id,  # 👈 add this
                "track_name": (t.track_name or "").strip(),
                "artist_name": (artist_name or "").strip(),
                "year_released": t.year_released,
            })
        planned, processed = [], 0

        # make these always defined
        xai_by_lang_id: Dict[str, Dict[int, str]] = {}
        xai_by_lang_key: Dict[str, Dict[tuple, str]] = {}

        if source == "xai" and HAS_XAI_TRACK and tracks:
            items = []
            for t in tracks:
                artist_name = load_artist_name(db, t)
                items.append({
                    "track_id": t.id,
                    "track_name": (t.track_name or "").strip(),
                    "artist_name": (artist_name or "").strip(),
                    "year_released": t.year_released,
                })

            for lang in langs:
                label = "Spanish" if lang == "es" else "Portuguese (Brazil)"
                results = get_track_details_from_xai(items, label) or []

                by_id: Dict[int, str] = {}
                by_key: Dict[tuple, str] = {}
                for r in results:
                    tid = r.get("track_id")
                    tn = (r.get("track_name") or "").strip()
                    an = (r.get("artist_name") or "").strip()
                    dt = (r.get("detail_text") or "").strip()
                    if isinstance(tid, int) and dt:
                        by_id[tid] = dt
                    if tn and an and dt:
                        by_key[(_norm_key(tn), _norm_key(an))] = dt

                xai_by_lang_id[lang] = by_id
                xai_by_lang_key[lang] = by_key

                logger.debug("XAI results mapped | lang=%s | count_id=%d | count_key=%d",
                             lang, len(by_id), len(by_key))

    for t in tracks:
        artist_name = load_artist_name(db, t)
        for lang in langs:
            loc = db.exec(
                select(TrackLocale)
                .where(TrackLocale.track_id == t.id)
                .where(TrackLocale.language_code == lang)
            ).first()

            if only_missing_text and loc and (loc.detail_text or "").strip():
                logger.info("⏭️ Skip track_id=%s | lang=%s reason=already has detail_text", t.id, lang)
                planned.append({
                    "track_id": t.id, "track": t.track_name, "language": lang,
                    "skipped": True, "reason": "already has detail_text"
                })
                continue

            text = None
            source_used = "seed"

            if source == "xai" and HAS_XAI_TRACK:
                # 1) prefer exact id match
                text = xai_by_lang_id.get(lang, {}).get(t.id)
                if text:
                    source_used = "xai"
                else:
                    # 2) fallback to normalized (track, artist)
                    k = (_norm_key(t.track_name or ""), _norm_key(artist_name or ""))
                    text = xai_by_lang_key.get(lang, {}).get(k)
                    if text:
                        source_used = "xai"

            # warn only if we requested xai but ended up using seed
            if source == "xai" and source_used != "xai":
                logger.warning(
                    "DETAIL PREP override: requested_source=xai but used=%s | track_id=%s lang=%s",
                    source_used, t.id, lang
                )

            if not text:
                text = generate_track_detail_seed(lang, t, artist_name)
                source_used = "seed"

            logger.debug(
                "🌱 Prepared detail_text | track_id=%s | lang=%s | source=%s",
                t.id, lang, source_used
            )

            planned.append({
                "track_id": t.id,
                "track": t.track_name,
                "artist": artist_name,
                "language": lang,
                "will_write": {"detail_text": True},
                "source": source_used,
            })

            if dry_run:
                continue

            if loc:
                logger.info("✏️ Updating detail_text | track_id=%s | lang=%s", t.id, lang)
                loc.detail_text = text
            else:
                logger.info("➕ Inserting detail_text | track_id=%s | lang=%s", t.id, lang)
                loc = TrackLocale(
                    track_id=t.id,
                    language_code=lang,
                    detail_text=text,
                )
                db.add(loc)

            db.commit()
            processed += 1

    # --- end for loops ---

    return {
        "processed": processed if not dry_run else len(planned),
        "dry_run": dry_run,
        "languages": langs,
        "offset": requested_offset,  # stable input offset
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
        logger.warning("🚫 No supported languages requested: %s", languages)
        return {"processed": 0, "note": "No supported languages requested."}

    if not (ELEVENLABS_API_KEY or "").strip():
        logger.error("❌ ELEVENLABS_API_KEY is missing; cannot synthesize.")
        return {"processed": 0, "note": "ELEVENLABS_API_KEY missing"}

    if not (ELEVEN_MODEL_ID or "").strip():
        logger.error("❌ ELEVEN_MODEL_ID is missing; cannot synthesize.")
        return {"processed": 0, "note": "ELEVEN_MODEL_ID missing"}

    tracks = pick_tracks(db, track_ids, limit, offset)
    requested_offset = offset
    logger.info(
        "🎧 Synth detail TTS | langs=%s | limit=%s offset=%s dry_run=%s overwrite=%s only_missing_tts=%s",
        langs, limit, requested_offset, dry_run, overwrite, only_missing_tts
    )
    logger.debug("Picked %d tracks (ids: %s...)", len(tracks), [t.id for t in tracks[:5]])

    planned: List[Dict[str, Any]] = []
    tts_errors: List[str] = []
    processed = 0
    skipped_existing = 0
    skipped_no_text = 0

    for t in tracks:
        artist_name = load_artist_name(db, t)

        for lang in langs:
            loc = db.exec(
                select(TrackLocale)
                .where(TrackLocale.track_id == t.id)
                .where(TrackLocale.language_code == lang)
            ).first()

            # choose text source (locale.detail_text preferred, else english fallback)
            text = (loc.detail_text if loc and (loc.detail_text or "").strip() else None) \
                   or (t.detail or "").strip()

            bucket = bucket_for("detail", lang)
            key    = compute_detail_key(db, t.id)

            already_has_tts = bool(loc and (loc.tts_key or "").strip())
            if only_missing_tts and already_has_tts:
                skipped_existing += 1
                logger.info("⏭️ Skip (only_missing_tts=True & already has tts) | track_id=%s lang=%s key=%s",
                            t.id, lang, getattr(loc, "tts_key", ""))
                continue
            if (not overwrite) and already_has_tts:
                skipped_existing += 1
                logger.info("⏭️ Skip (overwrite=False & already has tts) | track_id=%s lang=%s key=%s",
                            t.id, lang, getattr(loc, "tts_key", ""))
                continue

            planned.append({
                "track_id": t.id,
                "track": t.track_name,
                "artist": artist_name,
                "language": lang,
                "text_source": "locale" if (loc and (loc.detail_text or "").strip()) else "english_fallback",
                "bucket": bucket,
                "key": key,
                "will_synth": bool(text),
            })

            if dry_run:
                # nothing else to do for this item
                continue

            if not text:
                skipped_no_text += 1
                msg = f"track_id={t.id} lang={lang}: no text to synth"
                tts_errors.append(msg)
                logger.warning("⚠️ %s", msg)
                continue

            try:
                logger.debug("🔊 Synth start | track_id=%s lang=%s model=%s chars=%s",
                             t.id, lang, ELEVEN_MODEL_ID, len(text))
                mp3 = synth_to_mp3_bytes(
                    text=text,
                    lang=lang,
                    kind="detail",
                    api_key=ELEVENLABS_API_KEY or "",
                    model_id=ELEVEN_MODEL_ID,
                    retries=1,
                )
                if not mp3:
                    err = f"track_id={t.id} lang={lang}: ElevenLabs returned no audio"
                    tts_errors.append(err)
                    logger.error("❌ %s", err)
                    continue

                logger.debug("⬆️ Uploading %d bytes -> %s/%s", len(mp3), bucket, key)
                upload_bytes(bucket=bucket, key=key, data=mp3)

                if not loc:
                    loc = TrackLocale(
                        track_id=t.id, language_code=lang,
                        detail_text=text, tts_bucket=bucket, tts_key=key
                    )
                    db.add(loc)
                else:
                    loc.tts_bucket = bucket
                    loc.tts_key = key
                    if not (loc.detail_text or "").strip():
                        loc.detail_text = text

                db.commit()
                processed += 1
                logger.info("✅ Synth+uploaded | track_id=%s lang=%s key=%s", t.id, lang, key)

            except Exception as ex:
                db.rollback()
                err = f"track_id={t.id} lang={lang}: {type(ex).__name__}: {ex}"
                tts_errors.append(err)
                logger.exception("💥 TTS/upload error: %s", err)

    # If dry_run, "processed" reflects how many would be attempted
    processed_out = processed if not dry_run else len([p for p in planned if p.get("will_synth")])

    return {
        "processed": processed_out,
        "dry_run": dry_run,
        "languages": langs,
        "offset": requested_offset,  # 👈 use the stable offset
        "sample_planned_actions": planned[:10],
        "tts_errors": tts_errors[:25],
        "skipped_existing": skipped_existing,
        "skipped_no_text": skipped_no_text,
        "note": "(dry-run) no uploads performed" if dry_run else "track detail TTS synthesized/uploaded",
    }
