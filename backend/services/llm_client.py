# backend/services/llm_client.py
import os
import json
import re
import time
import logging
import httpx

logger = logging.getLogger(__name__)

# --- JSON extraction helpers -------------------------------------------------

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

# --- Provider calls ----------------------------------------------------------

_DEFAULT_TIMEOUT = float(os.getenv("LLM_HTTP_TIMEOUT", "90"))

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

    logger.info("llm_client: OpenAI request model=%s timeout=%.0fs prompt_chars=%d",
                model, _DEFAULT_TIMEOUT, len(prompt))

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as http:
            r = http.post(url, headers=headers, json=payload)
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
      - XAI_MODEL (optional, default: grok-beta)
    """
    api_key = os.environ["XAI_API_KEY"]
    model = os.getenv("XAI_MODEL", "grok-beta")

    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    logger.info("llm_client: xAI request model=%s timeout=%.0fs prompt_chars=%d",
                model, _DEFAULT_TIMEOUT, len(prompt))

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as http:
            r = http.post(url, headers=headers, json=payload)
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

# --- Public API --------------------------------------------------------------

def complete_json(prompt: str) -> dict:
    """
    Call your configured LLM and return a Python dict shaped like:
    {"pop":[...], "rock":[...]}

    Config:
      - LLM_PROVIDER in {"openai","xai","mock"} (default "openai")
      - For mock: MOCK_POPROCK_JSON must point to a local JSON file.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    logger.info("llm_client: provider=%s", provider)

    if provider == "mock":
        path = os.getenv("MOCK_POPROCK_JSON")
        if not path:
            logger.error("llm_client: MOCK_POPROCK_JSON not set while provider=mock")
            raise RuntimeError("MOCK_POPROCK_JSON env var not set for LLM_PROVIDER=mock")
        logger.info("llm_client: loading mock JSON from %s", path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug("llm_client: mock JSON loaded (top-level keys=%s)", list(data) if isinstance(data, dict) else type(data))
        return data

    if provider == "openai":
        return _openai_complete(prompt)

    if provider == "xai":
        return _xai_complete(prompt)

    logger.error("llm_client: unknown provider=%s", provider)
    raise NotImplementedError(f"Unknown LLM_PROVIDER: {provider}")
