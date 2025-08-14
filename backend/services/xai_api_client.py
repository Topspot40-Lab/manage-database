# backend/services/xai_api_client.py
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse
import os

from backend.config import (
    XAI_API_KEY,
    XAI_API_URL,
    DEFAULT_XAI_MODEL,
    TEMPERATURE_DEFAULT,
    TEST_JSON_DIR,                # pathlib.Path or str
    FALLBACK_TO_TEST_ON_XAI_ERROR,
    FALLBACK_TEST_FILE_NUMBER,
    XAI_TIMEOUT_SECONDS,          # read timeout (e.g., 120)
)
from .xai_errors import XAIQuotaError

logger = logging.getLogger("xai_api_client")

# ---- HTTPS enforcement -------------------------------------------------------------
ALLOW_HTTP = os.getenv("ALLOW_HTTP", "false").lower() == "true"

def _require_https(url: str, allowed_hosts=("localhost", "127.0.0.1")):
    u = urlparse(url)
    if u.scheme == "https":
        return
    if ALLOW_HTTP and (u.hostname in allowed_hosts) and u.scheme == "http":
        return
    raise ValueError(f"Insecure URL blocked: {url}")

# ---- Ensure TEST_JSON_DIR is a Path ------------------------------------------------
TEST_DIR: Path = Path(TEST_JSON_DIR) if not isinstance(TEST_JSON_DIR, Path) else TEST_JSON_DIR
if not TEST_DIR.exists():
    logger.warning("TEST_JSON_DIR does not exist: %s", TEST_DIR)

# ---- HTTP session with retries/backoff --------------------------------------------
_session = requests.Session()

_retries = Retry(
    total=3,               # a little more generous
    connect=3,
    read=3,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["POST"]),  # IMPORTANT: uppercase method names
    raise_on_status=False,
)

_adapter = HTTPAdapter(max_retries=_retries, pool_connections=20, pool_maxsize=20)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)  # harmless; keeps pools consistent

# ---- Helpers ----------------------------------------------------------------------
def _test_path(n: int) -> Path:
    return TEST_DIR / f"json_test_file_{n}.json"

def _load_test_json(test_file_number: int):
    p = _test_path(test_file_number)
    if not p.exists():
        raise FileNotFoundError(str(p))
    logger.warning("🧪 TEST MODE: Using %s", p)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def _first_available_test_file() -> Optional[int]:
    for n in range(1, 10):
        if _test_path(n).exists():
            return n
    return None

def _extract_content(body: Any) -> Any:
    """Tolerate different response shapes."""
    # If provider returns the array directly
    if isinstance(body, list):
        return body
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, TypeError, IndexError):
        pass
    for key in ("output", "content", "data"):
        if isinstance(body, dict) and key in body:
            return body[key]
    return body  # last resort

def _safe_json_parse_maybe_array(content: Any) -> Any:
    if isinstance(content, str):
        s = content.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                logger.debug("✅ XAI returned parsable JSON array")
                return parsed
            except json.JSONDecodeError:
                logger.warning("⚠️ Looked like JSON array but failed to parse; returning raw string")
    return content

def _fallback_or_raise(why: str, exc: Exception):
    """Fallback to a test file, else re-raise the original exception."""
    if not FALLBACK_TO_TEST_ON_XAI_ERROR:
        raise exc
    tf = FALLBACK_TEST_FILE_NUMBER or 0
    if tf > 0 and _test_path(tf).exists():
        logger.info("🛟 %s — falling back to test file #%s", why, tf)
        return _load_test_json(tf)
    auto = _first_available_test_file()
    if auto:
        logger.info("🛟 %s — configured test missing; using first available test file #%s", why, auto)
        return _load_test_json(auto)
    logger.error("❌ Fallback enabled but no test files found in %s", TEST_DIR)
    raise exc

# ---- Public API -------------------------------------------------------------------
def fetch_xai_tracks(prompt, test_file_number: int = 0):
    """
    Returns either:
      - a Python object (when test mode or when model returns JSON that we parse), or
      - a raw JSON string/object from the model (if not parsable here).
    """
    # Test mode short-circuit
    if test_file_number and test_file_number > 0:
        return _load_test_json(test_file_number)

    # Enforce HTTPS (except localhost when ALLOW_HTTP=true)
    _require_https(XAI_API_URL)

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

    connect_timeout = 10
    read_timeout = XAI_TIMEOUT_SECONDS

    try:
        logger.info("📡 XAI: sending request (non-stream)")
        t0 = time.monotonic()
        resp = _session.post(
            XAI_API_URL,
            json=payload,
            headers=headers,
            timeout=(connect_timeout, read_timeout),
        )
        elapsed = time.monotonic() - t0
        logger.info("📩 XAI: response %s in %.2fs", resp.status_code, elapsed)

        if resp.status_code in (402, 429):
            logger.error("❌ XAI quota/rate error: %s\n%s", resp.status_code, resp.text)
            raise XAIQuotaError(resp.status_code, "XAI quota or rate limit reached")

        if resp.status_code != 200:
            logger.error("❌ XAI request failed: %s\n%s", resp.status_code, resp.text)
            resp.raise_for_status()

        try:
            body = resp.json()
        except ValueError as e:
            logger.exception("❌ XAI returned non-JSON")
            return _fallback_or_raise("Bad JSON response", e)

        content = _extract_content(body)
        return _safe_json_parse_maybe_array(content)

    except XAIQuotaError as e:
        return _fallback_or_raise("XAI quota/rate limit", e)

    except requests.ReadTimeout as e:
        logger.exception("⌛ XAI read timeout after %ss", read_timeout)
        return _fallback_or_raise("Read timeout", e)

    except (requests.ConnectTimeout, requests.ConnectionError) as e:
        logger.exception("🌐 XAI connect/network error")
        return _fallback_or_raise("Network error", e)

    except requests.RequestException as e:
        logger.exception("❌ XAI HTTP error")
        return _fallback_or_raise("HTTP error", e)

    except (KeyError, ValueError, TypeError) as e:
        logger.exception("❌ Unexpected XAI response structure")
        raise
