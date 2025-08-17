# backend/services/elevenlabs_tts.py
import os
import time
import logging
from typing import Optional, Dict, Any

import requests
from backend.config import ELEVEN_MODEL_ID
from backend.services.tts_profiles import get_tts_profile

log = logging.getLogger("tts")
ELEVEN_BASE = "https://api.elevenlabs.io/v1"
_OFF = {"", "0", "false", "no", "off"}

def _is_placeholder(voice_id: Optional[str]) -> bool:
    if not voice_id:
        return True
    vid = str(voice_id).strip()
    # catch common placeholders like "<ES_INTRO_ID>"
    return vid.startswith("<") or vid.endswith(">") or "ID>" in vid or "YOUR_" in vid

def synth_to_mp3_bytes(
    text: str,
    lang: str,
    kind: str,
    api_key: str,
    *,
    voice_id: Optional[str] = None,
    model_id: Optional[str] = None,
    timeout: int = 45,
    retries: int = 1,
) -> bytes:
    """
    Synthesize `text` to MP3 via ElevenLabs.
    Returns b"" if disabled/misconfigured so callers can safely skip upload.
    """

    # Global kill switch (default OFF): export ELEVENLABS_ENABLE=true to enable
    if os.getenv("ELEVENLABS_ENABLE", "false").strip().lower() in _OFF:
        log.info("TTS disabled (ELEVENLABS_ENABLE=false): skipping %s/%s", lang, kind)
        return b""

    if not api_key:
        log.error("TTS aborted: ELEVENLABS_API_KEY missing for %s/%s", lang, kind)
        return b""

    # Load voice/profile (router can also override voice_id via kwarg)
    prof: Dict[str, Any] = get_tts_profile(lang, kind) or {}
    vid = voice_id or prof.get("voice_id")
    if _is_placeholder(vid):
        log.error("TTS skipped: invalid/placeholder voice_id for %s/%s -> %r", lang, kind, vid)
        return b""

    mid = model_id or ELEVEN_MODEL_ID or "eleven_multilingual_v2"
    settings = prof.get("settings", {}) or {}

    url = f"{ELEVEN_BASE}/text-to-speech/{vid}"
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {"text": text, "model_id": mid, "voice_settings": settings}

    # simple retry for 429/5xx
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            if attempt >= retries:
                log.error("TTS request exception (%s/%s): %s", lang, kind, e)
                return b""
            time.sleep(0.6 * (2 ** attempt))
            continue

        if resp.status_code == 200:
            return resp.content

        # Retry on transient errors
        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
            if attempt < retries:
                wait = 0.6 * (2 ** attempt)
                log.warning("TTS %s received %s, retrying in %.1fs (%s/%s)", url, resp.status_code, wait, lang, kind)
                time.sleep(wait)
                continue

        # Hard 4xx like 400 (often bad voice_id) → log and skip
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:200]
        log.error("TTS failed (%s/%s) %s → %s", lang, kind, resp.status_code, detail)
        return b""

    return b""
