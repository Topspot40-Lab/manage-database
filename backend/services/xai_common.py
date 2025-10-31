# backend/services/xai_common.py
import json
import requests
import logging
import time
from backend.config import XAI_API_KEY, XAI_API_URL

logger = logging.getLogger("XAI")

def _safe_json_loads(s: str):
    """Tries to load JSON even if wrapped in ```json ... ``` or stray text."""
    if not s or not isinstance(s, str):
        return None
    t = s.strip().strip("`").strip()
    try:
        return json.loads(t)
    except Exception:
        # try to isolate JSON array within stray text
        start = t.find("[")
        end = t.rfind("]")
        if start != -1 and end != -1:
            try:
                return json.loads(t[start:end + 1])
            except Exception:
                pass
    return None


def query_xai(prompt: str, model: str = "grok-2-latest", temperature: float = 0.3, max_retries: int = 1) -> list:
    """
    Sends a prompt to xAI and returns parsed JSON list.
    Includes retry, empty-content handling, and improved error logging.
    """
    if not XAI_API_KEY:
        logger.error("[XAI ERROR] Missing XAI_API_KEY.")
        return []

    payload = {
        "messages": [
            {"role": "system", "content": "You are an AI that returns ONLY valid JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        "model": model,
        "stream": False,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(XAI_API_URL, json=payload, headers=headers, timeout=90)
            response.raise_for_status()

            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if not content or not content.strip():
                logger.error("[XAI ERROR] Empty content body (attempt %d).", attempt + 1)
                logger.debug("🪶 Raw response text: %s", response.text[:400])
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return []

            parsed = _safe_json_loads(content)
            if isinstance(parsed, list):
                logger.debug("✅ Parsed JSON array of %d items (attempt %d)", len(parsed), attempt + 1)
                return parsed

            logger.error("[XAI ERROR] Content not valid JSON (attempt %d)", attempt + 1)
            logger.debug("🪶 Raw content: %s", content[:500])
            if attempt < max_retries:
                time.sleep(2)
                continue

        except requests.Timeout:
            logger.error("[XAI ERROR] Timeout (attempt %d)", attempt + 1)
            if attempt < max_retries:
                time.sleep(3)
                continue
        except requests.RequestException as e:
            logger.error("[XAI ERROR] Request failed: %s (attempt %d)", e, attempt + 1)
            if attempt < max_retries:
                time.sleep(3)
                continue
        except Exception as e:
            logger.exception("[XAI ERROR] Unexpected error (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries:
                time.sleep(2)
                continue

    logger.warning("[XAI] All attempts failed to return valid JSON.")
    return []
