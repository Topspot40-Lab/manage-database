# backend/services/xai_track_descriptions.py

from __future__ import annotations
import json
import logging
import time
from typing import List, Dict, Any
import requests

from backend.config import XAI_API_KEY, XAI_API_URL, BATCH_SIZE

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_RETRIES = 2
_BACKOFF_SECS = 1.5

def _canon_lang(lang: str) -> str:
    if not lang:
        return "en"
    s = lang.strip().lower()
    if s in {"ptbr", "pt-br", "pt_br"}:
        return "pt-BR"
    if s in {"es-mx", "es_ mx"}:
        return "es"
    return "en" if s.startswith("en") else s

def _strip_code_fences(s: str) -> str:
    # removes ```json ... ``` or ``` ... ```
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        # after strip, model may have 'json\n{...}'
        parts = s.split("\n", 1)
        if len(parts) == 2 and parts[0].lower() in {"json", "javascript"}:
            return parts[1].strip()
        return parts[-1].strip()
    return s

def _safe_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None

def _merge_intro_detail(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    intro = (src.get("intro") or "").strip()
    detail = (src.get("detail") or "").strip()
    if intro and not (dst.get("intro") or "").strip():
        dst["intro"] = intro
    if detail and not (dst.get("detail") or "").strip():
        dst["detail"] = detail

def get_track_descriptions_from_xai(track_data, language, category, genre):
    """
    Batches requests to XAI to fill 'intro' and 'detail' for each track.
    Keeps camelCase input fields intact (trackName, artistName).
    Only fills fields that are missing/empty.
    """
    lang = _canon_lang(language)
    tracks: List[Dict[str, Any]] = track_data if isinstance(track_data, list) else (track_data.get("tracks", []) or [])
    n = len(tracks)
    if n == 0:
        return {"language": lang, "category": category, "genre": genre, "tracks": tracks}

    for batch_index in range(0, n, BATCH_SIZE):
        batch = tracks[batch_index:batch_index + BATCH_SIZE]
        formatted_input = [
            {
                "rank": t.get("rank"),
                "category": category,
                "genre": genre,
                "trackName": t.get("trackName") or t.get("title") or t.get("track_name"),
                "artistName": t.get("artistName") or t.get("artist") or t.get("artist_name"),
            }
            for t in batch
        ]

        # Prompt tightened to enforce strict JSON array of objects with intro/detail only
        prompt = (
            f"Language: {lang}.\n"
            "For each item, generate two fields:\n"
            "  - intro: a short, varied one-sentence radio intro that mentions rank/category/genre context.\n"
            "  - detail: a 4–5 sentence Casey Kasem-style mini-story that does NOT repeat the intro info "
            "(avoid re-stating rank, track title, or artist name explicitly—use pronouns), include one concrete fact.\n\n"
            "Return ONLY valid JSON, no commentary, as an array matching the input order. "
            "Each array element must be an object with exactly keys: intro, detail.\n\n"
            f"Tracks:\n{json.dumps(formatted_input, ensure_ascii=False, indent=2)}"
        )

        payload = {
            "messages": [
                {"role": "system", "content": "You are a precise JSON generator. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.3,
        }

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    XAI_API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {XAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=_DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                raw = _strip_code_fences(content)
                parsed = _safe_json_loads(raw)

                if not isinstance(parsed, list):
                    raise ValueError("Model did not return a JSON array.")
                if len(parsed) != len(batch):
                    raise ValueError(f"Array length mismatch: got {len(parsed)}, expected {len(batch)}.")

                # merge results into original track dicts
                for i, desc in enumerate(parsed):
                    if not isinstance(desc, dict):
                        continue
                    _merge_intro_detail(batch[i], desc)

                logger.debug(
                    f"✅ XAI batch {batch_index // BATCH_SIZE + 1}: size={len(batch)} (attempt {attempt+1})"
                )
                break  # success

            except (requests.HTTPError, requests.Timeout) as e:
                logger.warning(
                    f"XAI HTTP error on batch {batch_index // BATCH_SIZE + 1} attempt {attempt+1}: {e}"
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECS * (attempt + 1))
                    continue
                logger.error(f"❌ Giving up batch {batch_index // BATCH_SIZE + 1} after retries.")
            except Exception as e:
                logger.error(
                    f"❌ Error processing batch {batch_index // BATCH_SIZE + 1} attempt {attempt+1}: {e}"
                )
                # No retry for non-HTTP parsing errors unless you want to.
                break

    return {
        "language": lang,
        "category": category,
        "genre": genre,
        "tracks": tracks,
    }
