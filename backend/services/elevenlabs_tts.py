# backend/services/elevenlabs_tts.py
import time
import logging
from typing import Optional, Dict, Any

import requests
from backend.config import (
    ELEVENLABS_ENABLE,   # global on/off (bool)
    ELEVEN_MODEL_ID,     # global default model (str)
    MODEL_BY_LANG,       # per-language model map (dict)
)
from backend.services.tts_profiles import get_tts_profile

log = logging.getLogger("tts")
ELEVEN_BASE = "https://api.elevenlabs.io/v1"

# Practical guardrails
_MIN_TEXT_CHARS = 20          # skip junk/stubs
_MAX_TEXT_CHARS = 5000        # ElevenLabs soft/hard limits vary; keep sane

def _is_placeholder(voice_id: Optional[str]) -> bool:
    if not voice_id:
        return True
    vid = str(voice_id).strip()
    # catch common placeholders like "<ES_INTRO_ID>"
    return vid.startswith("<") or vid.endswith(">") or "ID>" in vid or "YOUR_" in vid

def synth_to_mp3_bytes(
    *,
    text: str,
    lang: str,
    kind: str,                 # e.g. "artist", "track_intro", "track_detail"
    api_key: str,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    timeout: int = 45,
    retries: int = 1,
    enabled: Optional[bool] = None,     # None => use ELEVENLABS_ENABLE (from config)
    log_when_disabled: bool = False,    # keep quiet for dry-runs by default
) -> Optional[bytes]:
    """
    Synthesize `text` to MP3 via ElevenLabs.

    Returns:
        bytes  -> MP3 data on success
        None   -> when disabled, misconfigured, invalid input, or non-retryable error

    Model selection precedence:
        1) model_id arg
        2) TTS profile (get_tts_profile(lang, kind)).get("model_id")
        3) MODEL_BY_LANG.get(lang)  (from backend.config)
        4) ELEVEN_MODEL_ID          (global default from backend.config)
        5) "eleven_multilingual_v2" (hard default)
    """
    # Resolve enable flag from config unless explicitly overridden
    if enabled is None:
        enabled = bool(ELEVENLABS_ENABLE)
    if not enabled:
        if log_when_disabled:
            log.info("TTS disabled: skipping %s/%s", lang, kind)
        return None

    if not api_key:
        log.error("TTS aborted: ELEVENLABS_API_KEY missing for %s/%s", lang, kind)
        return None

    text = (text or "").strip()
    if len(text) < _MIN_TEXT_CHARS:
        log.warning("TTS skipped: text too short (%d chars) for %s/%s", len(text), lang, kind)
        return None
    if len(text) > _MAX_TEXT_CHARS:
        log.info("TTS truncating long text (%d→%d chars) for %s/%s", len(text), _MAX_TEXT_CHARS, lang, kind)
        text = text[:_MAX_TEXT_CHARS]

    # Resolve voice + settings (and allow profile-specific model override)
    prof: Dict[str, Any] = get_tts_profile(lang, kind) or {}
    vid = (voice_id or prof.get("voice_id") or "").strip()
    if _is_placeholder(vid):
        log.error("TTS skipped: invalid/placeholder voice_id for %s/%s -> %r", lang, kind, vid)
        return None

    mid = (
        model_id
        or prof.get("model_id")
        or MODEL_BY_LANG.get(lang)
        or ELEVEN_MODEL_ID
        or "eleven_multilingual_v2"
    )
    settings = prof.get("settings", {}) or {}

    url = f"{ELEVEN_BASE}/text-to-speech/{vid}"
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {"text": text, "model_id": mid, "voice_settings": settings}

    # simple capped exponential backoff
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            if attempt >= retries:
                log.error("TTS request exception (%s/%s): %s", lang, kind, e)
                return None
            wait = min(2.0 * (2 ** attempt), 6.0)
            time.sleep(wait)
            continue

        if resp.status_code == 200:
            return resp.content

        # Retry on transient errors
        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
            if attempt < retries:
                wait = min(0.8 * (2 ** attempt), 6.0)
                log.warning("TTS transient %s; retrying in %.1fs (%s/%s)", resp.status_code, wait, lang, kind)
                time.sleep(wait)
                continue

        # Hard 4xx like 400/401/403 → log and bail
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:300]
        log.error("TTS failed (%s/%s) %s → %s", lang, kind, resp.status_code, detail)
        return None

    return None
