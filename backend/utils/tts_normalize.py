import re
from typing import Literal

_LANG = Literal["en", "es"]

# Precompile patterns
_RE_HASH_NUM = re.compile(r"\B#(\d+)\b", re.IGNORECASE)
_RE_NO_NUM_EN = re.compile(r"\bNo\.\s*(\d+)\b", re.IGNORECASE)
_RE_NO_NUM_ES = re.compile(r"\bN[\.\s]*[º°o]?\s*(\d+)\b", re.IGNORECASE)  # N., N.º, N°, No, etc.

# We want to replace "bass" -> "base" only for the musical sense.
# Protect common "fish" contexts so we don't change them.
_PROTECT_FISH_BEFORE = r"(sea|striped|largemouth|smallmouth|white|black|rock)"
_PROTECT_FISH_AFTER  = r"(fishing|boat|boats|angler|anglers|tournament|lake|river|pro\s?shop[s]?)"

_RE_BASS_SAFE = re.compile(r"\b(bass)\b", re.IGNORECASE)
_RE_BASS_PROTECT_BEFORE = re.compile(rf"\b{_PROTECT_FISH_BEFORE}\s+bass\b", re.IGNORECASE)
_RE_BASS_PROTECT_AFTER  = re.compile(rf"\bbass\s+{_PROTECT_FISH_AFTER}\b", re.IGNORECASE)

def _preserve_case(replacement: str, original: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement.capitalize()
    return replacement

def _replace_bass(match: re.Match) -> str:
    """Replace 'bass'->'base' unless in a protected fish context nearby."""
    start, end = match.span()
    # Slice some context around the match to check fish-y phrases
    window_before = 20
    window_after = 20
    text = match.string
    left  = text[max(0, start - window_before):end]      # includes "bass"
    right = text[start:max(len(text), end + window_after)]
    # If "sea bass", "striped bass", etc. -> do NOT replace
    if _RE_BASS_PROTECT_BEFORE.search(left):
        return match.group(0)
    # If "bass fishing", "bass boat", etc. -> do NOT replace
    if _RE_BASS_PROTECT_AFTER.search(right):
        return match.group(0)
    # Otherwise, treat as musical bass
    return _preserve_case("base", match.group(0))

def normalize_tts_text(text: str, lang: _LANG = "en") -> str:
    """
    Normalize narration text for TTS so ElevenLabs reads it the way we intend.
      - '#14'       -> 'number 14' / 'número 14'
      - 'No. 14'    -> 'number 14' / 'número 14' (handles N., N.º, N°)
      - 'bass' (music) -> 'base' (avoids fish contexts like 'sea bass', 'bass fishing')

    Only call this for the text you send to TTS (keep original display text as-is if you like).
    """
    if not text:
        return text

    # Numbers
    if lang == "en":
        text = _RE_HASH_NUM.sub(r"number \1", text)
        text = _RE_NO_NUM_EN.sub(r"number \1", text)
    elif lang == "es":
        text = _RE_HASH_NUM.sub(r"número \1", text)
        # Accept several Spanish-ish "No." variants:
        text = _RE_NO_NUM_ES.sub(r"número \1", text)
    else:
        # default: be conservative (still fix hashtags universally)
        text = _RE_HASH_NUM.sub(r"number \1", text)

    # Musical bass -> base (protect “fish” contexts)
    text = _RE_BASS_SAFE.sub(_replace_bass, text)

    return text
