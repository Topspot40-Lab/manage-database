# backend/services/llm_client.py
import os
import json
import re
import httpx

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

    # 1) Try fenced block first
    m = _FENCED_OBJ_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # fall through to other strategies
            pass

    s = text.strip()

    # 2) If it starts with '{', try parse whole string
    if s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass

    # 3) If not starting with '{', jump to the first '{' and try from there
    idx = s.find("{")
    if idx == -1:
        raise ValueError("No JSON object found in response.")
    s = s[idx:]

    # 4) Bracket-match the first complete top-level object.
    #    Be careful to ignore braces inside JSON strings.
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

        # not in string
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
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    preview = candidate[:200].replace("\n", " ")
                    raise ValueError(
                        f"Found object but JSON parsing failed: {e}; preview: {preview}..."
                    )

    raise ValueError("Unbalanced braces; could not extract a complete JSON object.")

# --- Providers ---------------------------------------------------------------

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

    with httpx.Client(timeout=90) as http:
        r = http.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    text = data["choices"][0]["message"]["content"]
    return _extract_json_object(text)

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

    with httpx.Client(timeout=90) as http:
        r = http.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    text = data["choices"][0]["message"]["content"]
    return _extract_json_object(text)

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

    if provider == "mock":
        path = os.getenv("MOCK_POPROCK_JSON")
        if not path:
            raise RuntimeError("MOCK_POPROCK_JSON env var not set for LLM_PROVIDER=mock")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if provider == "openai":
        return _openai_complete(prompt)

    if provider == "xai":
        return _xai_complete(prompt)

    raise NotImplementedError(f"Unknown LLM_PROVIDER: {provider}")
