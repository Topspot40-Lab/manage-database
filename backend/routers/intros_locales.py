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

_SENT_TRACK = "[[TRACK_NAME]]"
_SENT_ARTIST = "[[ARTIST_NAME]]"
# --- in _protect_one, compile wrapper with (?i) at start and insert the raw pattern string ---
def _protect_one(text: str, name: str, sentinel: str) -> str:
    if not name:
        return text
    core = _name_core_regex(name)
    if core is None:
        return text
    wrapper = re.compile(
        rf'(?i)(?P<pre>["\'_*«»“”‘’()\[\]<>]*)'
        rf'(?P<core>{core})'
        rf'(?P<post>["\'_*«»“”‘’()\[\]<>]*)'
    )
    return wrapper.sub(lambda m: f'{m.group("pre")}{sentinel}{m.group("post")}', text)

# --- replace the old _name_core_regex with this (returns a pattern STRING) ---
def _name_core_regex(name: str) -> Optional[str]:
    """
    Build a punctuation-agnostic core pattern for the name, WITHOUT inline flags.
    Example return: r"\b(Forever\W+and\W+Ever\W+Amen)\b"
    """
    if not name:
        return None
    tokens = re.findall(r"\w+", name, flags=re.UNICODE)
    if not tokens:
        return None
    core = r"\W+".join(map(re.escape, tokens))
    return rf"\b({core})\b"



def _protect_names(text: str, track: str, artist: str) -> str:
    # First, strip markdown so *Name* becomes Name and can be matched
    base = strip_inline_markdown(text)
    base = _protect_one(base, track, _SENT_TRACK)
    base = _protect_one(base, artist, _SENT_ARTIST)
    return base

def _strip_llm_preface(s: str) -> str:
    """Remove short 'reviewed text' headers and keep the main paragraph."""
    s = s.strip()
    # Remove one-line headers ending with colon (Portuguese/Spanish/English variants)
    s = re.sub(
        r'^\s*(?:texto|vers[aã]o|revisad[oa]|revis[aã]o)\b.*?:\s*\n+',
        '',
        s,
        flags=re.IGNORECASE
    )
    # If multiple paragraphs, keep the longest non-empty
    parts = [p.strip() for p in re.split(r'\n{2,}', s) if p.strip()]
    if len(parts) >= 1:
        s = max(parts, key=len)
    return s

# --- in _force_exact_casing, compile with flags instead of relying on inline (?i) ---
def _force_exact_casing(text: str, track: str, artist: str) -> str:
    def fix(s: str, name: str) -> str:
        pat = _name_core_regex(name)
        if not name or pat is None:
            return s
        return re.compile(pat, flags=re.IGNORECASE).sub(name, s)
    text = fix(text, track)
    text = fix(text, artist)
    return text


def _restore_names(text: str, track: str, artist: str) -> str:
    text = text.replace(_SENT_TRACK, track)
    text = text.replace(_SENT_ARTIST, artist)
    return text

# put these near _MD_EMPH_RE
_MD_EMPH_RE   = re.compile(r'(?<!\\)([*_])((?:(?!\1).)+?)\1')   # *text* or _text_, not escaped
_BACKTICK_RE  = re.compile(r'(?<!\\)`([^`]+?)`')                # `code`, not escaped

def strip_inline_markdown(s: str) -> str:
    if not s:
        return s
    s = _MD_EMPH_RE.sub(r"\2", s)
    s = _BACKTICK_RE.sub(r"\1", s)
    return s

# --- Allow localized rank phrases for es/pt-BR; disallow 'number' there ---
def _rank_ok(text: str, rank: int, lang: str) -> bool:
    r = str(rank)

    def has(p: str) -> bool:
        return re.search(p, text, flags=re.IGNORECASE) is not None

    if lang in ("es", "pt-BR"):
        # Accept common localized variants:
        #   "número 4", "número: 4", "número-4"
        #   "nº 4" / "n.º 4" (º or °), and "no. 4" (seen in some texts)
        pats = [
            rf"\bn[úu]mero\s*[:\-]?\s*{r}\b",  # número 4 / número: 4
            rf"\bn[º°]\.?\s*{r}\b",            # nº 4 / n.º 4
            rf"\bno\.?\s*{r}\b",               # no. 4
        ]
        return any(has(p) for p in pats)

    # Default (English or others): allow "number 4", "number: 4", "number-4"
    return has(rf"\bnumber\s*[:\-]?\s*{r}\b")



def qa_intro(text: str, rank: int, track: str, artist: str, lang: str) -> List[str]:
    errs: List[str] = []
    if "#" in text:
        errs.append("Contains '#'.")
    if not _rank_ok(text, rank, lang):
        errs.append(f"Missing rank phrase for {lang} (expected 'number {rank}' or locale variant).")
    if track and track not in text:
        errs.append("Track name altered/missing.")
    if artist and artist not in text:
        errs.append("Artist name altered/missing.")
    return errs

def _qa_relaxed(text: str) -> List[str]:
    return ["Contains '#'."] if "#" in text else []

def _looks_like_english(s: str) -> bool:
    # super-light heuristic: lots of common English glue-words
    EN_HINTS = r"\b(the|and|of|to|in|with|for|on|at|from|this|that|is|are|was|were|as|by|it|its|his|her|their)\b"

    return bool(re.search(EN_HINTS, s, flags=re.IGNORECASE)) and not re.search(r"[áéíóúñçãõ]", s)

def _ensure_language(text: str, lang: str, system: str, user: str, *, max_retry: int = 1) -> str:
    if lang not in ("es", "pt-BR"):
        return text
    bad = _looks_like_english(text)
    if not bad:
        return text
    # one stricter retry
    strict_user = user + f"\n\nHARD OUTPUT RULE: Respond ONLY in {lang}. Do not use English."
    try:
        retried = call_llm(system=system, user=strict_user).strip()
        return retried if not _looks_like_english(retried) else text
    except Exception:
        return text

def _smart_title(s: str) -> str:
    # tiny helper: title-case but leave all-caps acronyms and small words alone
    SMALL = {"and","or","the","of","in","on","for","a","an"}
    parts = re.split(r"(\W+)", s)
    out = []
    for i, p in enumerate(parts):
        if not p or not p.isalpha():
            out.append(p); continue
        upper = p.isupper()
        lower = p.islower()
        if upper: out.append(p)                 # keep acronyms
        elif lower and p.lower() in SMALL and i != 0: out.append(p.lower())
        else: out.append(p.capitalize())
    return "".join(out)

def _canonicalize_name(name: str) -> str:
    return _smart_title(name) if name and name.islower() else name

_OPENERS_ES = [
    "Con un toque", "Con un aire", "Llegando con", "Presentamos", "Aquí llega", "Atentos"
]
_OPENERS_PT = [
    "Com uma carga", "Trazendo", "Chegando com", "Apresentamos", "Aqui vem", "Prepare-se"
]

def _looks_repetitive_open(text: str, lang: str) -> bool:
    starters = _OPENERS_ES if lang == "es" else _OPENERS_PT
    return any(text.strip().lower().startswith(s.lower()) for s in starters)

def _repolish_if_repetitive(text: str, lang: str, rank: int, track: str, artist: str) -> str:
    if not _looks_repetitive_open(text, lang):
        return text
    system = f"Rewrite in {lang} with a different opening phrase than common clichés. Keep facts identical."
    user = f"""Text:
{text}

Rules:
- Keep the exact phrase 'number {rank}'.
- No '#'.
- Do not change song or artist names: {track} — {artist}.
- 1–3 sentences. Announcer tone. TTS-friendly.
- Use a different opening than the original."""
    try:
        alt = call_llm(system=system, user=user).strip()
        return alt if len(alt) >= 20 else text
    except Exception:
        return text

def _quote_title_once(text: str, title: str) -> str:
    # If title appears unquoted but not quoted, add single quotes around first occurrence
    if title and (title in text) and (f"'{title}'" not in text) and (f"“{title}”" not in text) and (f"\"{title}\"" not in text):
        return text.replace(title, f"'{title}'", 1)
    return text

def translate_intro_from_en(en_text: str, lang: str, rank: int, track: str, artist: str) -> str:
    protected = _protect_names(en_text, track, artist)
    system = f"Translate English to {lang}. Natural, concise. Do NOT add or remove facts."
    user = f"""Original:
{protected}

Constraints (hard):
- Keep the exact phrase 'number {rank}' when referring to rank.
- Never use '#'.
- DO NOT translate or alter song/artist names; placeholders appear as [[TRACK_NAME]] and [[ARTIST_NAME]] and must remain EXACTLY as written.
- Preserve diacritics; 1–3 sentences; announcer tone; TTS-friendly."""
    draft = call_llm(system=system, user=user).strip()
    draft = _ensure_language(draft, lang, system, user)
    draft = _strip_llm_brackets(draft)

    # 👇 add this line
    draft = localize_rank_word(draft, lang)

    out = _restore_names(draft, track, artist)
    out = _force_exact_casing(out, track, artist)
    if "#" in out:
        out = out.replace("#", "number ")
    if rank and not _rank_ok(out, rank, lang):
        out = f"{out.rstrip('.')} (number {rank})"
    return out
def polish_locale(text: str, lang: str, rank: int, track: str, artist: str) -> str:
    system = f"Polish this {lang} text for radio-host delivery. Keep facts identical."
    user = f"""Text:
{text}

Hard constraints:
- Keep exact 'number {rank}' (do not translate it).
- No '#'.
- Do not change song or artist names: {track} — {artist}.
- Keep 1–3 sentences.
- If placeholders [[TRACK_NAME]] or [[ARTIST_NAME]] appear, keep them EXACTLY as written.
Output only the revised text. Do not add explanations, headings, labels, language tags, or quotes."""
    polished = call_llm(system=system, user=user).strip()
    polished = _ensure_language(polished, lang, system, user)
    polished = _strip_llm_preface(polished)
    polished = _strip_llm_brackets(polished)

    # 👇 add this line
    polished = localize_rank_word(polished, lang)

    polished = _restore_names(polished, track, artist)
    polished = _force_exact_casing(polished, track, artist)
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
    strip_markdown_for_tts: bool = Query(True, description="Strip simple inline markdown (* _ `) before save/preview"),
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

        # Canonicalize once right after fetching from DB
        track_name = _canonicalize_name((getattr(tk, "track_name", "") or "").strip())
        artist_name = _canonicalize_name((getattr(ar, "artist_name", "") or getattr(ar, "name", "") or "").strip())
        rank = int(getattr(tr, "ranking", 0) or 0)

        for lang in langs:
            def run_qa(txt: str) -> List[str]:
                if rank > 0 and track_name and artist_name:
                    return qa_intro(txt, rank, track_name, artist_name, lang)
                return _qa_relaxed(txt)

            existing = db.exec(
                select(TrackRankingLocale)
                .where(
                    TrackRankingLocale.track_ranking_id == tr.id,
                    TrackRankingLocale.language_code == lang
                )
            ).first()

            if only_missing_text and existing and (existing.intro_text or "").strip():
                skipped += 1
                preview.append({
                    "track_ranking_id": tr.id, "lang": lang,
                    "action": "skip (already present)"
                })
                continue

            try:
                text = translate_intro_from_en(intro_en, lang, rank, track_name, artist_name)
                if polish:
                    polished = polish_locale(text, lang, rank, track_name, artist_name)
                    polished = _repolish_if_repetitive(polished, lang, rank, track_name, artist_name)
                    if not run_qa(polished):
                        text = polished

                errs = run_qa(text)
                if errs:
                    preview_text = strip_inline_markdown(text) if strip_markdown_for_tts else text
                    preview.append({
                        "track_ranking_id": tr.id, "lang": lang,
                        "action": "qa-failed",
                        "text_sample": preview_text[:120] + ("…" if len(preview_text) > 120 else "")
                    })
                    errors.append(f"tr_id={tr.id} lang={lang} QA fail: {', '.join(errs)}")
                    continue

                action = "update" if (existing and overwrite) else (
                    "insert" if not existing else "skip (exists, overwrite=false)")
                # Enforce final casing before preview/save
                text = _force_exact_casing(text, track_name, artist_name)
                text = _quote_title_once(text, track_name)  # 👈 insert here

                # Ensure it ends with proper punctuation
                if text and text[-1] not in ".!?…":
                    text += "."

                preview_text = strip_inline_markdown(text) if strip_markdown_for_tts else text
                preview.append({
                    "track_ranking_id": tr.id, "lang": lang,
                    "action": action,
                    "text_sample": preview_text[:120] + ("…" if len(preview_text) > 120 else "")
                })

                if dry_run:
                    continue

                if existing and not overwrite:
                    skipped += 1
                    continue

                to_save = strip_inline_markdown(text) if strip_markdown_for_tts else text
                to_save = localize_rank_word(to_save, lang)  # 👈 optional safeguard
                to_save = _force_exact_casing(to_save, track_name, artist_name)
                to_save = _quote_title_once(to_save, track_name)

                if to_save and to_save[-1] not in ".!?…":
                    to_save += "."

                upsert_intro(db, tr.id, lang, to_save, overwrite=overwrite)

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
        "note": "Dry-run: no DB writes" if dry_run else "Translations upserted",
        "strip_markdown_for_tts": strip_markdown_for_tts

    }

# backend/services/locales_postprocess.py
import re

_NUMBER_RE = re.compile(r"\bnumber\s*[:#]?\s*(\d+)\b", flags=re.IGNORECASE)

def localize_rank_word(text: str, lang: str) -> str:
    """
    Replace 'number 4'/'Number: 4'/'number #4' with 'número 4'
    for es and pt-BR outputs. Leaves everything else untouched.
    """
    if lang in ("es", "pt-BR"):
        return _NUMBER_RE.sub(r"número \1", text)
    return text
