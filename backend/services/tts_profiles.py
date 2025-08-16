# backend/services/tts_profiles.py
from backend.config import TTS_PROFILES
def resolve_lang(lang: str) -> str:
    if lang in ("pt", "pt_br", "ptbr"): return "pt-BR"
    return lang or "en"

def get_tts_profile(lang: str, kind: str) -> dict:
    lang = resolve_lang(lang)
    profs = TTS_PROFILES.get(lang) or TTS_PROFILES["en"]
    return profs.get(kind) or profs["detail"]  # fallback to a sane default
