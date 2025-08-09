import requests
import logging
import json
from backend.config import (
    XAI_API_KEY,
    XAI_API_URL,
    DEFAULT_XAI_MODEL,
    TEMPERATURE_DEFAULT,
    TEST_JSON_DIR,
    FALLBACK_TO_TEST_ON_XAI_ERROR,
    FALLBACK_TEST_FILE_NUMBER,
    XAI_TIMEOUT_SECONDS,
)
from .xai_errors import XAIQuotaError

logger = logging.getLogger("xai_api_client")

def _load_test_json(test_file_number: int):
    test_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
    logger.warning(f"🧪 TEST MODE: Using {test_path}")
    with open(test_path, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_xai_tracks(prompt, test_file_number: int = 0):
    """
    Returns either:
      - a Python object (when test mode or when model returns JSON that we parse), or
      - a raw JSON string from the model (if not parsable here).
    Callers should be ready for either (you already handle this in your step layer).
    """
    # ── Test mode short-circuit
    if test_file_number and test_file_number > 0:
        return _load_test_json(test_file_number)

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are an AI that strictly returns valid JSON arrays with no extra text."},
            {"role": "user", "content": prompt},
        ],
        "model": DEFAULT_XAI_MODEL,
        "temperature": TEMPERATURE_DEFAULT,
        "stream": False,
    }

    try:
        logger.info("📡 XAI: sending request (non-stream)")
        resp = requests.post(XAI_API_URL, json=payload, headers=headers, timeout=XAI_TIMEOUT_SECONDS)

        # Quota / rate limits
        if resp.status_code in (402, 429):
            logger.error(f"❌ XAI quota/rate error: {resp.status_code}")
            logger.error(resp.text)
            raise XAIQuotaError(resp.status_code, "XAI quota or rate limit reached")

        # Other HTTP failures
        if resp.status_code != 200:
            logger.error(f"❌ XAI request failed: {resp.status_code}")
            logger.error(resp.text)
            resp.raise_for_status()  # will raise HTTPError

        body = resp.json()
        content = body["choices"][0]["message"]["content"]

        # Try to parse if it's JSON text; otherwise return raw and let caller parse
        content_str = content.strip() if isinstance(content, str) else content
        if isinstance(content_str, str) and content_str.startswith("["):
            try:
                parsed = json.loads(content_str)
                logger.debug("✅ XAI returned parsable JSON array")
                return parsed
            except json.JSONDecodeError:
                logger.warning("⚠️ XAI content looked like JSON but failed to parse; returning raw string")

        return content
    except XAIQuotaError:
        if FALLBACK_TO_TEST_ON_XAI_ERROR:
            tf = FALLBACK_TEST_FILE_NUMBER or 1
            logger.info(f"🛟 XAI quota/rate limit — falling back to test file #{tf}")
            return _load_test_json(tf)
        raise
    except requests.RequestException:
        logger.exception("❌ XAI HTTP/network error")
        if FALLBACK_TO_TEST_ON_XAI_ERROR:
            tf = FALLBACK_TEST_FILE_NUMBER or 1
            logger.info(f"🛟 Network error — falling back to test file #{tf}")
            return _load_test_json(tf)
        raise
    except (KeyError, ValueError):
        logger.exception("❌ Unexpected XAI response structure")
        raise
