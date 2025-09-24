# backend/utils/naming.py
from __future__ import annotations
import re
import unicodedata


LANG_CODE_MAP = {
    # English
    "en": "en", "english": "en",

    # Spanish
    "es": "es", "spanish": "es", "español": "es", "espanol": "es",
    "sp": "es", "es-mx": "es",

    # Portuguese
    "pt": "pt", "portuguese": "pt", "português": "pt", "portugues": "pt",
    "pt-br": "pt",

    # French
    "fr": "fr", "french": "fr", "français": "fr", "francais": "fr",

    # German
    "de": "de", "german": "de", "deutsch": "de",

    # Italian
    "it": "it", "italian": "it", "italiano": "it",

    # Japanese
    "ja": "ja", "japanese": "ja", "日本語": "ja",

    # Korean
    "ko": "ko", "korean": "ko", "한국어": "ko",

    # Chinese (default to simplified)
    "zh": "zh", "chinese": "zh", "中文": "zh",
    "zh-cn": "zh", "zh-hans": "zh", "zh-tw": "zh", "zh-hant": "zh",
}

_VALID_TWO_LETTER = {"en","es","pt","fr","de","it","ja","ko","zh"}

_slug_re = re.compile(r"[^a-z0-9]+")

def normalize_language_code(s: str | None) -> str:
    """Return ISO 639-1 two-letter code for major languages; default to 'en'."""
    if not s:
        return "en"
    key = s.strip().lower()
    # Known names & variants
    if key in LANG_CODE_MAP:
        return LANG_CODE_MAP[key]
    # Already a supported 2-letter code
    if key in _VALID_TWO_LETTER:
        return key
    # Fallback (main languages only)
    return "en"

def slug_underscore(text: str | None) -> str:
    """Lowercase, strip accents, replace non-alnum with underscores, collapse repeats."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = _slug_re.sub("_", text).strip("_")
    return re.sub(r"_+", "_", text)

# --- Canonical language handling for TopSpot ---
try:
    from topspot_shared.lang import canon_lang as normalize_language_code_canon  # -> 'en'|'es'|'pt-BR'
# Prefer the shared package (keeps Isaiah and your backend in sync).

except Exception:
    def normalize_language_code_canon(s: str | None) -> str:
        if not s:
            return "en"
        raw = s.strip()
        key = raw.lower()
        if key in {"pt", "ptbr", "pt_br", "pt-br", "portuguese", "português", "portugues"}:
            return "pt-BR"
        norm2 = normalize_language_code(raw)  # your 2-letter normalizer
        if norm2 == "pt":
            return "pt-BR"
        if norm2 in {"en", "es"}:
            return norm2
        return "en"


def lang_to_bucket_slug(lang: str) -> str:
    """
    Convert canonical language ('en'|'es'|'pt-BR') to your storage slug:
      en→'en', es→'es', pt-BR→'ptbr'
    """
    canon = normalize_language_code_canon(lang)
    return {"pt-BR": "ptbr"}.get(canon, canon)

