# backend/routers/intros_locales.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
import logging, time, requests
import re  # ensure imported at top

from backend.database import get_db
from backend.models.dbmodels import TrackRanking, TrackRankingLocale, Track, Artist
from backend.services.locales_common import (
    strip_inline_markdown, strip_llm_brackets, force_exact_casing,
    quote_title_once, rebalance_parens_quotes, localize_rank_word, rank_ok
)
from backend.services.qafix_es import qa_fix_spanish_intro, qa_intro_errors_es
from backend.services.tts_prep import prepare_for_tts_es

from backend.config import XAI_API_KEY, XAI_API_URL, XAI_MODEL, TEMPERATURE_DEFAULT
from backend.services.qafix_es import ensure_artist_after_title

TR  = TrackRanking.__table__
TRL = TrackRankingLocale.__table__
log = logging.getLogger("intros_locales")
router = APIRouter(tags=["Locales"], prefix="/locales")

# ── XAI client (unchanged behavior) ──────────────────────────────────────────
def call_llm(system: str, user: str) -> str:
    api_key = (XAI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Missing XAI_API_KEY env var")
    payload = {
        "model": XAI_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user",   "content": user}],
        "temperature": TEMPERATURE_DEFAULT,
        "max_tokens": 240,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(XAI_API_URL, headers=headers, json=payload, timeout=(10, 60))
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = r
                time.sleep(1.5 * (attempt + 1)); continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as ex:
            last_err = ex
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f"XAI request failed: {type(ex).__name__}: {ex}")
        except (KeyError, IndexError) as ex:
            body = getattr(last_err, 'text', '')[:300]
            raise RuntimeError(f"Unexpected XAI response shape: {ex}; body={body}")
    raise RuntimeError(f"XAI request failed after retries: {getattr(last_err, 'status_code','?')}")

# ── PG upsert helper ─────────────────────────────────────────────────────────
def upsert_intro(db: Session, tr_id: int, lang: str, text: str, overwrite: bool) -> None:
    ins = pg_insert(TRL).values(track_ranking_id=tr_id, language_code=lang, intro_text=text)
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

# ── Translation/polish helpers (minimal) ─────────────────────────────────────
def translate_intro_from_en(en_text: str, rank: int, track: str, artist: str, lang: str="es") -> str:
    system = f"Translate English to {lang}. Natural, concise, 1–3 sentences, announcer tone. Do NOT add or remove facts."
    user = f"""Original:
{en_text}

Constraints:
- Keep the exact song and artist names: {track} — {artist} (do not translate or recase).
- Include a localized rank phrase (e.g., 'número {rank}') once. Never use '#'.
- TTS-friendly; no markdown; no headings; no lists."""
    out = call_llm(system, user).strip()
    out = strip_llm_brackets(out)
    out = localize_rank_word(out, lang)
    return out

def polish_locale(text: str, lang: str, rank: int, track: str, artist: str) -> str:
    system = f"Polish this {lang} text for radio-host delivery. Keep facts identical."
    user = f"""Text:
{text}

Hard rules:
- Keep EXACT song/artist spellings: {track} — {artist}.
- Include exactly one localized rank phrase (e.g., 'número {rank}').
- No '#'. 1–3 sentences. TTS-friendly. No markdown or labels."""
    out = call_llm(system, user).strip()
    out = strip_llm_brackets(out)
    out = localize_rank_word(out, lang)
    return out

# ── Endpoint: ES only (Swagger shows only 'es') ──────────────────────────────
@router.post(
    "/translate",
    summary="Translate EN intros to ES and upsert into track_ranking_locale"
)
def translate_intros_from_english(
    lang: Literal["es"] = Query("es", description="Language (fixed to es)"),
    track_ranking_ids: Optional[List[int]] = Query(None),
    limit: int = Query(50, ge=1, le=2200),
    offset: int = Query(0, ge=0),
    only_missing_text: bool = Query(True),
    overwrite: bool = Query(False, description="If true, update existing locales; else insert only"),
    dry_run: bool = Query(True),
    polish: bool = Query(False, description="Run a light polish pass after translation"),
    strip_markdown_for_tts: bool = Query(True, description="Strip simple inline markdown before save/preview"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    # 1) Select EN intros
    q = (
        select(TrackRanking, Track, Artist)
        .where(TR.c.intro.isnot(None), func.length(func.trim(TR.c.intro)) > 0)
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
        return {"processed": 0, "langs": [lang], "note": "No rows found (missing English intro or filter too narrow)."}

    created = updated = skipped = 0
    preview: List[Dict[str, Any]] = []
    errors: List[str] = []

    for tr, tk, ar in rows:
        intro_en = (tr.intro or "").strip()
        if not intro_en:
            skipped += 1
            preview.append({"track_ranking_id": tr.id, "action": "skip (no English intro)"})
            continue

        track_name  = (getattr(tk, "track_name", "") or "").strip()
        artist_name = (getattr(ar, "artist_name", "") or getattr(ar, "name", "") or "").strip()
        rank = int(getattr(tr, "ranking", 0) or 0)

        existing = db.exec(
            select(TrackRankingLocale)
            .where(TrackRankingLocale.track_ranking_id == tr.id,
                   TrackRankingLocale.language_code == lang)
        ).first()

        if only_missing_text and existing and (existing.intro_text or "").strip():
            skipped += 1
            preview.append({"track_ranking_id": tr.id, "lang": lang, "action": "skip (already present)"})
            continue

        try:
            # Translate → optional polish → ES QA auto-fix
            text = translate_intro_from_en(intro_en, rank, track_name, artist_name, lang="es")
            if polish:
                text = polish_locale(text, "es", rank, track_name, artist_name)

            # final hardening
            text, changed, fix_issues = qa_fix_spanish_intro(
                text, rank=rank, track_name=track_name, artist_name=artist_name
            )
            # Final guard against stray '#'
            text = re.sub(r"#\s*(\d+)\b", r"número \g<1>", text)
            text = re.sub(r"(?<!\w)#(?!\d)", "", text)

            # QA check (defensive)
            qa_errs = qa_intro_errors_es(text, rank, track_name, artist_name)
            # --- AUTO-REPAIR for common QA fails ---
            if qa_errs:
                repaired = False

                # If rank phrase is missing, append the Spanish phrase once.
                if any("Missing localized rank phrase" in e for e in qa_errs) and rank:
                    text = f"{text.rstrip('.')} (número {rank})."
                    repaired = True

                # If artist is missing/mutated, force the "'Title' de ARTIST" pattern.
                if any("Artist name altered/missing" in e for e in qa_errs) and track_name and artist_name:
                    text = ensure_artist_after_title(text, track_name, artist_name)
                    text = force_exact_casing(text, track_name, artist_name)
                    text = rebalance_parens_quotes(text)
                    repaired = True

                if repaired:
                    # Run the fixer again and re-check QA
                    text, _, _ = qa_fix_spanish_intro(
                        text, rank=rank, track_name=track_name, artist_name=artist_name
                    )
                    qa_errs = qa_intro_errors_es(text, rank, track_name, artist_name)
            # --- /AUTO-REPAIR ---

            if qa_errs:
                sample = strip_inline_markdown(text) if strip_markdown_for_tts else text
                preview.append({
                    "track_ranking_id": tr.id, "lang": lang, "action": "qa-failed",
                    "text_sample": sample[:120] + ("…" if len(sample) > 120 else "")
                })
                errors.append(f"tr_id={tr.id} lang={lang} QA fail: {', '.join(qa_errs)}")
                continue

            # Final Spanish TTS prep (locks casing/quotes, balances punctuation,
            # ensures rank phrase, and normalizes numbers/decades to Spanish words)
            text = prepare_for_tts_es(
                text,
                rank=rank,
                track_name=track_name,
                artist_name=artist_name,
                strip_markdown=True,  # keep true so previews/DB are TTS-safe
                number_normalize=True,  # makes "número 1" → "número uno", "años 50" → "años cincuenta"
            )

            # preview
            sample = strip_inline_markdown(text) if strip_markdown_for_tts else text
            action = "update" if (existing and overwrite) else ("insert" if not existing else "skip (exists, overwrite=false)")
            preview.append({"track_ranking_id": tr.id, "lang": lang, "action": action, "text_sample": sample[:120] + ("…" if len(sample) > 120 else "")})

            if dry_run:
                continue

            if existing and not overwrite:
                skipped += 1
                continue

            to_save = text

            if rank and not rank_ok(to_save, rank, "es"):
                # belt-and-suspenders: append the right phrase if somehow missing
                to_save = f"{to_save.rstrip('.')} (número {rank})."
            upsert_intro(db, tr.id, lang, to_save, overwrite=overwrite)

            if existing:
                updated += 1 if overwrite else 0
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
        "langs": [lang],
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
        "overwrite": overwrite,
        "polish": polish,
        "sample": preview[:12],
        "errors": errors[:10],
        "note": "Dry-run: no DB writes" if dry_run else "Translations upserted",
        "strip_markdown_for_tts": strip_markdown_for_tts,
    }
