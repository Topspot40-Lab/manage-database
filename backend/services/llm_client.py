# backend/services/llm_client.py
import os
import json
import re
import time
import logging
import httpx
from httpx import ReadTimeout, ConnectTimeout, RemoteProtocolError

from backend.config import (
    XAI_API_KEY,
    XAI_MODEL,
    # OPENAI_API_KEY, OPENAI_MODEL,   # ok to keep for future flexibility
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Environment / tunables
# ─────────────────────────────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default

# Shared HTTP tuning (used for both xAI and OpenAI)
XAI_CONNECT_TIMEOUT = _env_int("XAI_CONNECT_TIMEOUT", 15)
XAI_READ_TIMEOUT    = _env_int("XAI_READ_TIMEOUT", 180)   # main fix (bigger reads)
XAI_WRITE_TIMEOUT   = _env_int("XAI_WRITE_TIMEOUT", 60)
XAI_POOL_TIMEOUT    = _env_int("XAI_POOL_TIMEOUT", 180)
XAI_MAX_RETRIES     = _env_int("XAI_MAX_RETRIES", 5)
XAI_BACKOFF_FACTOR  = _env_float("XAI_BACKOFF_FACTOR", 1.8)

# Legacy default for ad-hoc single-use clients (kept for compatibility)
_DEFAULT_TIMEOUT = float(os.getenv("LLM_HTTP_TIMEOUT", "90"))

# One shared client (HTTP/2 + connection pooling + gzip/br)
_HTTP = httpx.Client(
    http2=True,
    timeout=httpx.Timeout(
        connect=XAI_CONNECT_TIMEOUT,
        read=XAI_READ_TIMEOUT,
        write=XAI_WRITE_TIMEOUT,
        pool=XAI_POOL_TIMEOUT,
    ),
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
    },
)

def _post_with_retries(url: str, *, headers: dict, json_payload: dict) -> httpx.Response:
    """POST with exponential-backoff retries on transient network errors."""
    attempt = 0
    while True:
        try:
            return _HTTP.post(url, headers=headers, json=json_payload)
        except (ReadTimeout, ConnectTimeout, RemoteProtocolError) as e:
            attempt += 1
            if attempt > XAI_MAX_RETRIES:
                raise
            sleep_s = XAI_BACKOFF_FACTOR ** attempt
            logger.warning(
                "HTTP retry %d/%d after %s — sleeping %.1fs",
                attempt, XAI_MAX_RETRIES, type(e).__name__, sleep_s
            )
            time.sleep(sleep_s)

# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

# Accepts fenced ```json or ```jsonc blocks
_FENCED_OBJ_RE = re.compile(
    r"```(?:json|jsonc)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE
)

def _extract_json_object(text: str) -> dict:
    """
    Parse a JSON object out of a model response.

    - Accepts plain JSON or fenced ```json blocks.
    - Tries direct json.loads first.
    - Falls back to bracket-matching the first complete top-level object.
    - Ignores braces that appear inside JSON strings.
    """
    if not isinstance(text, str):
        raise ValueError("LLM response is not text")

    logger.debug("llm_client: starting JSON extraction (len=%d)", len(text))

    # 1) Try fenced block first
    m = _FENCED_OBJ_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        logger.debug("llm_client: found fenced json block (len=%d)", len(candidate))
        try:
            parsed = json.loads(candidate)
            logger.debug("llm_client: fenced block parsed OK")
            return parsed
        except json.JSONDecodeError as e:
            logger.debug("llm_client: fenced block JSON decode failed: %s", e)

    s = text.strip()

    # 2) If it starts with '{', try parse whole string
    if s.startswith("{"):
        try:
            parsed = json.loads(s)
            logger.debug("llm_client: full-string JSON parsed OK")
            return parsed
        except json.JSONDecodeError as e:
            logger.debug("llm_client: full-string JSON decode failed: %s", e)

    # 3) If not starting with '{', jump to the first '{' and try from there
    idx = s.find("{")
    if idx == -1:
        raise ValueError("No JSON object found in response.")
    s = s[idx:]

    # 4) Bracket-match the first complete top-level object.
    depth = 0
    start = None
    in_string = False
    escape = False

    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = s[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                    logger.debug("llm_client: bracket-matched JSON parsed OK (len=%d)", len(candidate))
                    return parsed
                except json.JSONDecodeError as e:
                    preview = candidate[:200].replace("\n", " ")
                    logger.debug("llm_client: bracket-matched JSON decode failed: %s; preview=%r...", e, preview)
                    raise ValueError(
                        f"Found object but JSON parsing failed: {e}; preview: {preview}..."
                    )

    raise ValueError("Unbalanced braces; could not extract a complete JSON object.")

# ─────────────────────────────────────────────────────────────────────────────
# Provider calls
# ─────────────────────────────────────────────────────────────────────────────

def _openai_complete(prompt: str) -> dict:
    """
    Calls OpenAI Chat Completions via HTTP and asks for a JSON object.
    Env:
      - OPENAI_API_KEY (required)
      - OPENAI_MODEL (optional, default: gpt-4o-mini)
    """
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }

    logger.info(
        "llm_client: OpenAI request model=%s timeouts(c/r/w/p)=%ds/%ds/%ds/%ds prompt_chars=%d",
        model, XAI_CONNECT_TIMEOUT, XAI_READ_TIMEOUT, XAI_WRITE_TIMEOUT, XAI_POOL_TIMEOUT, len(prompt)
    )

    t0 = time.perf_counter()
    try:
        r = _post_with_retries(url, headers=headers, json_payload=payload)
        r.raise_for_status()
        data = r.json()
        elapsed = time.perf_counter() - t0
        logger.info("llm_client: OpenAI response OK in %.2fs", elapsed)

        text = data["choices"][0]["message"]["content"]
        logger.debug("llm_client: OpenAI content len=%d", len(text))
        return _extract_json_object(text)
    except Exception:
        logger.exception("llm_client: OpenAI call failed")
        raise

def _xai_complete(prompt: str) -> dict:
    """
    Calls xAI Grok via HTTP and asks for JSON in the content.
    Env:
      - XAI_API_KEY (required)
      - XAI_MODEL (optional, default from backend.config)
      - XAI_* timeout/retry envs (optional)
    """
    api_key = XAI_API_KEY
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set (provider=xai).")
    model = XAI_MODEL

    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
        # Optionally: "max_tokens": 8192,
        # "stream": False,
    }

    logger.info(
        "llm_client: xAI request model=%s timeouts(c/r/w/p)=%ds/%ds/%ds/%ds prompt_chars=%d",
        model, XAI_CONNECT_TIMEOUT, XAI_READ_TIMEOUT, XAI_WRITE_TIMEOUT, XAI_POOL_TIMEOUT, len(prompt)
    )

    t0 = time.perf_counter()
    try:
        r = _post_with_retries(url, headers=headers, json_payload=payload)
        r.raise_for_status()
        data = r.json()
        elapsed = time.perf_counter() - t0
        logger.info("llm_client: xAI response OK in %.2fs", elapsed)

        text = data["choices"][0]["message"]["content"]
        logger.debug("llm_client: xAI content len=%d", len(text))
        return _extract_json_object(text)
    except Exception:
        logger.exception("llm_client: xAI call failed")
        raise

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def complete_json(prompt: str, provider: str | None = None) -> dict:
    """
    Ask the configured LLM to return a JSON object.
    Honors LLM_PROVIDER env:
      - xai (default)
      - openai
      - mock (reads MOCK_POPROCK_JSON path)
    """
    cfg_provider = os.getenv("LLM_PROVIDER", "xai").lower()
    if provider and provider.lower() != cfg_provider:
        logger.warning(
            "complete_json: ignoring provider=%s; using LLM_PROVIDER=%s",
            provider, cfg_provider
        )

    provider = cfg_provider
    logger.info("llm_client: provider=%s", provider)

    if provider == "mock":
        path = os.getenv("MOCK_POPROCK_JSON")
        if not path:
            raise RuntimeError("MOCK_POPROCK_JSON env var not set for LLM_PROVIDER=mock")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if provider == "xai":
        return _xai_complete(prompt)

    if provider == "openai":
        return _openai_complete(prompt)

    raise NotImplementedError(f"Unknown LLM_PROVIDER: {provider}")
