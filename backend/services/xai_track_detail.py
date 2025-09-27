# backend/services/xai_track_detail.py
import json
import logging
from typing import List, Dict, Any
import os
import requests  # swap for your xAI SDK if you have one

logger = logging.getLogger("xai_track_detail")

# ─────────────────────────────────────────────────────────────────────────────
# Per-track detail filler used by collections/decade pipelines
# ─────────────────────────────────────────────────────────────────────────────
import backend.config as cfg
from backend.services.prompts.text_descriptions import build_detail_prompt, to_xai_messages

def _xai_chat_complete(messages: List[Dict[str, str]], temperature: float | None = None, max_tokens: int | None = None) -> str:
    """
    Minimal xAI chat wrapper using requests. Returns assistant text content.
    """
    api_key = os.getenv("XAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY missing")

    temperature = cfg.TEMPERATURE_DEFAULT if temperature is None else temperature
    max_tokens  = min(2048, getattr(cfg, "MAX_TOKENS_DEFAULT", 1024)) if max_tokens is None else max_tokens

    resp = requests.post(
        cfg.XAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": cfg.XAI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=cfg.XAI_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()


def get_track_details_from_xai(tracks: List[Dict[str, Any]], language: str = "en") -> None:
    """
    Mutates each track dict to set t['detail'] using build_detail_prompt().
    Matches the signature expected by xai_descriptions.get_collection_descriptions_from_xai.
    """
    if not tracks:
        logger.debug("🧠 detail: no tracks to process")
        return

    # Tunables from config (rich 2–3 sentences by default)
    sentences_min = getattr(cfg, "DETAIL_SENTENCES_MIN", 2)
    sentences_max = getattr(cfg, "DETAIL_SENTENCES_MAX", 3)
    words_min     = getattr(cfg, "DETAIL_WORDS_MIN", 60)
    words_max     = getattr(cfg, "DETAIL_WORDS_MAX", 90)
    forbid_new    = getattr(cfg, "DETAIL_FORBID_NEW_FACTS", False)
    folk_mode     = getattr(cfg, "DETAIL_FOLK_ACOUSTIC_MODE", False)

    filled = 0
    for t in tracks:
        # Skip if pre-filled
        if isinstance(t.get("detail"), str) and t["detail"].strip():
            continue

        track_name  = (t.get("track_name") or t.get("title") or "").strip()
        artist_name = (t.get("artist_name") or t.get("artistName") or t.get("artist") or "").strip()
        album_name  = (t.get("album_name") or t.get("albumName") or None)
        year_rel    = t.get("year_released") or t.get("year")
        genre_ctx   = t.get("_genre_context") or getattr(cfg, "DETAIL_GENRE_CONTEXT_DEFAULT", "") or None

        if not (track_name and artist_name):
            continue

        yr = None
        if isinstance(year_rel, int):
            yr = year_rel
        elif isinstance(year_rel, str) and year_rel.isdigit():
            yr = int(year_rel)

        prompt = build_detail_prompt(
            track_name=track_name,
            artist_name=artist_name,
            album_name=album_name,
            year_released=yr,
            language=language,
            sentences_min=sentences_min,
            sentences_max=sentences_max,
            words_min=words_min,
            words_max=words_max,
            folk_acoustic_mode=folk_mode,
            forbid_new_facts=forbid_new,
            genre_context=genre_ctx,  # ← theme hint (e.g., "Power Ballads")
        )
        messages = to_xai_messages(prompt)

        try:
            text = _xai_chat_complete(messages)
            if text:
                t["detail"] = text
                filled += 1
                logger.debug("🧠 detail: filled for %s — %d chars", track_name, len(text))
        except requests.HTTPError as he:
            logger.warning("🧠 detail: HTTP %s for '%s': %s",
                           getattr(he.response, "status_code", "?"), track_name, he)
        except Exception as e:
            logger.warning("🧠 detail: xAI error on '%s': %s", track_name, e)

    logger.info("🧠 detail: populated %d/%d tracks", filled, len(tracks))


# --- Add below your existing get_track_details_from_xai ----------------------
from typing import Optional
from sqlmodel import Session, select

# Try to import models flexibly (your project names have varied)
try:
    from backend.models.dbmodels import Track, Artist, TrackLocale  # preferred
except Exception:
    try:
        from backend.models.dbmodels import Track, Artist, TrackLocale       # fallback
    except Exception:
        Track = Artist = TrackLocale = None  # type: ignore

_LANG_LABELS = {
    "en": "English",
    "es": "Spanish (Mexico)",
    "pt-br": "Portuguese (Brazil)",
}
_LANG_ALIASES = {
    "english": "en", "en": "en",
    "spanish": "es", "es": "es", "es-mx": "es",
    "portuguese": "pt-br", "pt": "pt-br", "pt-br": "pt-br", "português": "pt-br",
}
def _norm_lang(s: Optional[str]) -> str:
    if not s: return "en"
    return _LANG_ALIASES.get(s.strip().lower(), s.strip().lower())

def _lang_label(code: str) -> str:
    return _LANG_LABELS.get(code, "English")

def regenerate_missing_track_details(
    db: Session,
    *,
    language: str = "English",
    limit: int = 100,
    offset: int = 0,
    overwrite: bool = False,   # if False, skip rows that already have text
    dry_run: bool = False,
) -> int:
    """
    Finds tracks missing locale 'detail' text for the requested language,
    generates blurbs via get_track_details_from_xai, and upserts into TrackLocale.
    Returns the number of rows written (or that would be written in dry_run).
    """
    lang_code = _norm_lang(language)        # "English" -> "en", etc.
    lang_label = _lang_label(lang_code)     # "en" -> "English"

    if Track is None or Artist is None or TrackLocale is None:
        logger.error("Required models not importable (Track/Artist/TrackLocale).")
        return 0

    # Build a query for tracks needing detail text in this language
    # TrackLocale assumed to have columns: track_id, lang, detail_text
    # If your column names differ, tweak here.
    tl = TrackLocale
    t  = Track
    a  = Artist

    # existing locale rows for this lang
    q = (
        select(t.id, t.track_name, a.artist_name, t.year_released, tl.detail_text)
        .join(a, a.id == t.artist_id)
        .join(tl, tl.track_id == t.id, isouter=True)
        .where(
            ( (tl.lang == lang_code) & ( (tl.detail_text == None) | (tl.detail_text == "") ) )  # missing in this lang
            | (tl.lang == None)  # no locale row at all
        )
        .order_by(t.id)
    )

    rows = db.exec(q).all()
    if not rows:
        logger.info("✅ No tracks missing detail text for lang=%s", lang_code)
        return 0

    # Create a distinct list of items to send to XAI
    items = []
    seen = set()
    for (track_id, track_name, artist_name, year_released, detail_text) in rows:
        if not overwrite and detail_text:
            continue  # already has text and we are not overwriting
        if track_id in seen:
            continue
        seen.add(track_id)
        items.append({
            "track_id": track_id,
            "track_name": (track_name or "").strip(),
            "artist_name": (artist_name or "").strip(),
            "year_released": year_released,
        })

    if not items:
        logger.info("✅ Nothing to do (either none missing or overwrite=False skipped all).")
        return 0

    # Batch call to your existing LLM helper
    results = get_track_details_from_xai_batch(items, target_language_label=lang_label)

    if dry_run:
        logger.info("🧪 dry_run=True — would write %d locale detail rows for %s", len(results), lang_code)
        return len(results)

    # Upsert results into TrackLocale (insert new or update existing)
    updated = 0
    by_id = {r["track_id"]: r for r in results if r.get("detail_text")}
    if not by_id:
        logger.warning("xAI returned no usable results.")
        return 0

    # For each track_id, either update existing locale row or insert one
    for track_id, payload in by_id.items():
        text = payload["detail_text"].strip()
        if not text:
            continue

        # Find existing locale row for (track_id, lang)
        existing = db.exec(
            select(tl).where((tl.track_id == track_id) & (tl.lang == lang_code))
        ).first()

        if existing:
            if not existing.detail_text or overwrite:
                existing.detail_text = text
                updated += 1
        else:
            # Insert new locale row
            obj = tl(track_id=track_id, lang=lang_code, detail_text=text)
            db.add(obj)
            updated += 1

    db.commit()
    logger.info("✅ Wrote %d locale detail rows for %s", updated, lang_code)
    return updated


XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
XAI_MODEL   = os.getenv("XAI_MODEL", "grok-2-latest").strip()  # adjust if needed

_JSON_SCHEMA_HELP = (
    "Return ONLY a JSON array. No commentary. No markdown. "
    "Each item MUST be an object with keys: track_id (int), track_name (str), "
    "artist_name (str), detail_text (str)."
)

def _safe_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        # Handle ```json ... ``` wrappers or stray backticks
        t = s.strip().strip("`")
        try:
            return json.loads(t)
        except Exception:
            return None

def get_track_details_from_xai_batch(items: List[Dict[str, Any]], target_language_label: str) -> List[Dict[str, Any]]:
    """
    items: [{"track_id": int, "track_name": str, "artist_name": str, "year_released": int|None}, ...]
    returns: [{"track_id": int, "track_name": str, "artist_name": str, "detail_text": str}, ...]
    """
    if not XAI_API_KEY:
        logger.error("XAI_API_KEY missing; cannot call xAI")
        return []

    if not items:
        logger.warning("get_track_details_from_xai called with empty items")
        return []

    # Keep prompt deterministic and schema-focused
    system = (
        "You generate concise, engaging track detail blurbs for a music app. "
        f"Write in {target_language_label}. {_JSON_SCHEMA_HELP}"
    )

    # Only pass fields we actually need; always include track_id to ensure stable mapping
    slim = [{
        "track_id": it.get("track_id"),
        "track_name": (it.get("track_name") or "").strip(),
        "artist_name": (it.get("artist_name") or "").strip(),
        "year_released": it.get("year_released"),
    } for it in items if (it.get("track_name") and it.get("artist_name"))]

    logger.debug("📦 [Batch 1] Creating track details for tracks %s to %s",
                 slim[0]["track_id"], slim[-1]["track_id"])

    user = (
        "For each input item, output an element with the same track_id, plus track_name, artist_name, "
        "and a detail_text in the requested language (1-2 sentences, no quotes around the title unless necessary). "
        "Avoid DJ patter or station plugs.\n\n"
        "INPUT:\n" + json.dumps(slim, ensure_ascii=False) + "\n\nOUTPUT:"
    )

    try:
        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",  # replace with your actual endpoint if different
            headers={"Authorization": f"Bearer {XAI_API_KEY}"},
            json={
                "model": XAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 1200,
            },
            timeout=60,
        )
        if resp.status_code >= 400:
            logger.error("xAI HTTP %s: %s", resp.status_code, resp.text[:500])
            return []

        data = resp.json()
        content = (data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")).strip()

        # Try strict JSON first
        parsed = _safe_json_loads(content)
        if isinstance(parsed, list):
            out = []
            for r in parsed:
                tid = r.get("track_id")
                tn  = (r.get("track_name") or "").strip()
                an  = (r.get("artist_name") or "").strip()
                dt  = (r.get("detail_text") or "").strip()
                if isinstance(tid, int) and tn and an and dt:
                    out.append({"track_id": tid, "track_name": tn, "artist_name": an, "detail_text": dt})
                else:
                    logger.warning("xAI item invalid/partial: %r", r)
            logger.debug("✅ Parsed XAI JSON items=%d", len(out))
            return out

        # Fallback: model returned prose (like your log). Convert to 1-item result per input.
        # We distribute the same content across inputs or leave empty if nothing came back.
        if content:
            logger.debug("ℹ️ xAI returned non-JSON; wrapping into fallback results")
            # naive split if the model emitted multiple blurbs separated by blank lines
            chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
            out = []
            for i, it in enumerate(slim):
                blurb = chunks[i] if i < len(chunks) else chunks[-1] if chunks else ""
                if not blurb:
                    continue
                out.append({
                    "track_id": it["track_id"],
                    "track_name": it["track_name"],
                    "artist_name": it["artist_name"],
                    "detail_text": blurb
                })
            logger.debug("🟨 Fallback built items=%d from prose", len(out))
            return out

        logger.warning("xAI returned empty content")
        return []

    except Exception as ex:
        logger.exception("xAI call failed: %s", ex)
        return []
