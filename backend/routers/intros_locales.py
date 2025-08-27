# backend/routers/intros_locales.py
from typing import Any, Dict, List, Optional
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

# ✅ use your actual modules
from backend.database import get_db
from backend.models.dbmodels import TrackRanking, TrackRankingLocale, Track, Artist

# SQLAlchemy Tables (helps IDE understand .isnot/.asc/.in_)
TR  = TrackRanking.__table__
TRL = TrackRankingLocale.__table__

import re

# Matches <<...>>, <<'...'>>, <<"...">> (with optional spaces)
_BRACKET_WRAP_RE = re.compile(r"<<\s*(['\"]?)([^<>]+?)\1\s*>>")

def _strip_llm_brackets(text: str) -> str:
    """
    Remove LLM-added angle-bracket wrappers like:
      <<Randy Travis>>, <<'Forever and Ever Amen'>>, <<"A Song">>
    → returns the inner text without brackets/quotes.
    """
    return _BRACKET_WRAP_RE.sub(r"\2", text)




# --- XAI client ---
import time, requests
from backend.config import XAI_API_KEY, XAI_API_URL, XAI_MODEL, TEMPERATURE_DEFAULT
import logging
log = logging.getLogger("intros_locales")

def call_llm(system: str, user: str) -> str:
    """
    Translate/polish via XAI (Grok). Returns plain text content.
    Retries on 429/5xx with exponential backoff.
    """
    api_key = (XAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Missing XAI_API_KEY env var")

    url = XAI_API_URL  # from config: https://api.x.ai/v1/chat/completions
    payload = {
        "model": XAI_MODEL,            # from config, defaults to grok-3-latest
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": TEMPERATURE_DEFAULT,
        "max_tokens": 240,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if log.isEnabledFor(logging.DEBUG):
        log.debug("POST %s model=%s", url, payload["model"])

    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=(10, 60))
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = r
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as ex:
            last_err = ex
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"XAI request failed: {type(ex).__name__}: {ex}")
        except (KeyError, IndexError) as ex:
            raise RuntimeError(
                f"Unexpected XAI response shape: {ex}; body={getattr(last_err, 'text', '')[:300]}"
            )

    raise RuntimeError(
        f"XAI request failed after retries: "
        f"{getattr(last_err, 'status_code', '?')} {getattr(last_err, 'text', '')[:300]}"
    )

router = APIRouter()

# --- Swagger dropdown for languages ---
class LocaleEnum(str, Enum):
    es = "es"
    pt_BR = "pt-BR"

# -------- PG upsert helper ----------
def upsert_intro(db: Session, tr_id: int, lang: str, text: str, overwrite: bool) -> None:
    ins = pg_insert(TRL).values(
        track_ranking_id=tr_id,
        language_code=lang,
        intro_text=text
    )
    stmt = (
        ins.on_conflict_do_update(
            index_elements=[TRL.c.track_ranking_id, TRL.c.language_code],
            set_={"intro_text": text}
        ) if overwrite else
        ins.on_conflict_do_nothing(
            index_elements=[TRL.c.track_ranking_id, TRL.c.language_code]
        )
    )
    db.exec(stmt)

# --- reuse _normalize_langs from artist_locales (with safe fallback) ---
try:
    from backend.routers.artist_locales import _normalize_langs as _normalize_langs_base
except Exception:
    def _normalize_langs_base(langs: List[str]) -> List[str]:
        SUPPORTED_LANGS = {"es", "pt-BR"}
        out, seen = [], set()
        for l in langs or []:
            if l in SUPPORTED_LANGS and l not in seen:
                out.append(l); seen.add(l)
        return out

# -------- Helpers for name protection & QA ----------
import re

_SENT_TRACK = "[[TRACK_NAME]]"
_SENT_ARTIST = "[[ARTIST_NAME]]"

# normalize any stray placeholder variants the LLM might emit
_VARIANT_PATTERNS = [
    re.compile(r"<<\s*'?TRACK_NAME'?\s*>>", re.IGNORECASE),
    re.compile(r"<<\s*\"?TRACK_NAME\"?\s*>>", re.IGNORECASE),
    re.compile(r"<<\s*'?ARTIST_NAME'?\s*>>", re.IGNORECASE),
    re.compile(r"<<\s*\"?ARTIST_NAME\"?\s*>>", re.IGNORECASE),
]

def _protect_names(text: str, track: str, artist: str) -> str:
    # Replace exact substrings; if either is empty/None, skip
    if track:
        text = text.replace(track, _SENT_TRACK)
    if artist:
        text = text.replace(artist, _SENT_ARTIST)
    return text

def _normalize_placeholders(text: str) -> str:
    # Map common variants back to our sentinels
    text = _VARIANT_PATTERNS[0].sub(_SENT_TRACK, text)
    text = _VARIANT_PATTERNS[1].sub(_SENT_TRACK, text)
    text = _VARIANT_PATTERNS[2].sub(_SENT_ARTIST, text)
    text = _VARIANT_PATTERNS[3].sub(_SENT_ARTIST, text)
    # Also handle cases like <<'Forever and Ever Amen'>> where the model reinserted the real name.
    # If the text still contains any <<...>>, strip the brackets to reveal the name.
    text = re.sub(r"<<\s*'([^>]+?)'\s*>>", r"\1", text)
    text = re.sub(r"<<\s*\"([^>]+?)\"\s*>>", r"\1", text)
    return text

def _restore_names(text: str, track: str, artist: str) -> str:
    text = text.replace(_SENT_TRACK, track)
    text = text.replace(_SENT_ARTIST, artist)
    return text

def qa_intro(text: str, rank: int, track: str, artist: str) -> List[str]:
    errs: List[str] = []
    if "#" in text:
        errs.append("Contains '#'.")
    if f"number {rank}" not in text:
        errs.append(f"Missing literal 'number {rank}'.")
    if track and track not in text:
        errs.append("Track name altered/missing.")
    if artist and artist not in text:
        errs.append("Artist name altered/missing.")
    return errs

def _qa_relaxed(text: str) -> List[str]:
    return ["Contains '#'."] if "#" in text else []

def translate_intro_from_en(en_text: str, lang: str, rank: int, track: str, artist: str) -> str:
    protected = _protect_names(en_text, track, artist)
    system = f"Translate English to {lang}. Natural, concise. Do NOT add or remove facts."
    user = f"""
Original:
{protected}

Constraints (hard):
- Keep the exact phrase 'number {rank}' when referring to rank.
- Never use '#'.
- DO NOT translate or alter song/artist names (marked with <<...>>).
- Preserve diacritics; 1–3 sentences; announcer tone; TTS-friendly.
"""
    draft = call_llm(system=system, user=user).strip()

    # 👇 normalize any <<...>> / <<'...'> etc. the model added
    draft = _strip_llm_brackets(draft)

    out = _restore_names(draft, track, artist)
    if "#" in out:
        out = out.replace("#", "number ")
    if rank and f"number {rank}" not in out:
        out = f"{out.rstrip('.')} (number {rank})"
    return out


def polish_locale(text: str, lang: str, rank: int, track: str, artist: str) -> str:
    system = f"Polish this {lang} text for radio-host delivery. Keep facts identical."
    user = f"""
Text:
{text}

Hard constraints:
- Keep exact 'number {rank}' (do not translate it).
- No '#'.
- Do not change song or artist names: {track} — {artist}.
- Keep 1–3 sentences.
"""
    polished = call_llm(system=system, user=user).strip()

    # 👇 strip any lingering wrappers before restore/QA
    polished = _strip_llm_brackets(polished)
    polished = _restore_names(polished, track, artist)
    return polished

# ------------- Endpoint -------------------------------------------

@router.post(
    "/intros/translate",
    summary="Translate EN intros in track_ranking → upsert ES/PT-BR in track_ranking_locale"
)

def translate_intros_from_english(
    languages: List[LocaleEnum] = Query([LocaleEnum.es, LocaleEnum.pt_BR]),
    track_ranking_ids: Optional[List[int]] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    only_missing_text: bool = Query(True),
    overwrite: bool = Query(False, description="If true, update existing locales; if false, insert only."),
    dry_run: bool = Query(True),
    polish: bool = Query(True, description="Run a light localization pass after translation"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    # Convert Enum -> canonical strings and normalize (dedupe/order)
    langs = _normalize_langs_base([l.value for l in languages])
    if not langs:
        return {"processed": 0, "note": "No languages provided (after normalization)."}

    # 1) Select TrackRanking rows that have a non-empty English intro
    q = (
        select(TrackRanking, Track, Artist)
        .where(
            TR.c.intro.isnot(None),
            func.length(func.trim(TR.c.intro)) > 0
        )
        .join(Track, Track.id == TrackRanking.track_id)
        .join(Artist, Artist.id == Track.artist_id)
        .order_by(TR.c.id.asc())
    )
    if track_ranking_ids:
        q = q.where(TR.c.id.in_(track_ranking_ids))
    else:
        q = q.limit(limit).offset(offset)

    rows = db.exec(q).all()
    if not rows:
        return {"processed": 0, "note": "No rows found (missing English intro or filter too narrow)."}

    created = updated = skipped = 0
    preview: List[Dict[str, Any]] = []
    errors: List[str] = []

    for tr, tk, ar in rows:
        intro_en = (tr.intro or "").strip()
        if not intro_en:
            skipped += 1
            preview.append({"track_ranking_id": tr.id, "action": "skip (no English intro)"})
            continue

        track_name = (getattr(tk, "track_name", "") or "").strip()
        artist_name = (getattr(ar, "artist_name", "") or getattr(ar, "name", "") or "").strip()
        rank = int(getattr(tr, "ranking", 0) or 0)

        # Choose QA function: strict if we have rank+names; relaxed otherwise
        def run_qa(txt: str) -> List[str]:
            if rank > 0 and track_name and artist_name:
                return qa_intro(txt, rank, track_name, artist_name)
            return _qa_relaxed(txt)

        for lang in langs:
            # Check if a row exists already
            existing = db.exec(
                select(TrackRankingLocale)
                .where(
                    TrackRankingLocale.track_ranking_id == tr.id,
                    TrackRankingLocale.language_code == lang
                )
            ).first()

            # Honor only_missing_text: skip generation when text already present
            if only_missing_text and existing and (existing.intro_text or "").strip():
                skipped += 1
                preview.append({
                    "track_ranking_id": tr.id, "lang": lang,
                    "action": "skip (already present)"
                })
                continue

            # 2) Translate (hybrid)
            try:
                text = translate_intro_from_en(intro_en, lang, rank, track_name, artist_name)
                if polish:
                    polished = polish_locale(text, lang, rank, track_name, artist_name)
                    if not run_qa(polished):
                        text = polished

                # final QA
                errs = run_qa(text)
                if errs:
                    errors.append(f"tr_id={tr.id} lang={lang} QA fail: {', '.join(errs)}")
                    preview.append({
                        "track_ranking_id": tr.id, "lang": lang, "action": "qa-failed",
                        "text_sample": text[:120] + ("…" if len(text) > 120 else "")
                    })
                    continue

                # Decide action label for preview
                if existing:
                    action = "update" if overwrite else "skip (exists, overwrite=false)"
                else:
                    action = "insert"

                preview.append({
                    "track_ranking_id": tr.id, "lang": lang,
                    "action": action,
                    "text_sample": text[:120] + ("…" if len(text) > 120 else "")
                })

                if dry_run:
                    continue

                # 3) Write (insert-only or upsert)
                if existing and not overwrite:
                    skipped += 1
                    continue

                upsert_intro(db, tr.id, lang, text, overwrite=overwrite)

                # Counters based on existence
                if existing:
                    if overwrite:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    created += 1

            except Exception as ex:
                errors.append(f"tr_id={tr.id} lang={lang} error: {type(ex).__name__}: {ex}")

    if not dry_run:
        try:
            db.commit()
        except Exception as ex:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Commit failed: {ex}")

    return {
        "processed": len(rows),
        "langs": langs,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
        "overwrite": overwrite,
        "polish": polish,
        "sample": preview[: min(12, len(preview))],
        "errors": errors[:10],
        "note": "Dry-run: no DB writes" if dry_run else "Translations upserted"
    }
