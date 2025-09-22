# backend/services/locales_common.py
from __future__ import annotations
import re
from typing import Optional, List

# ── Simple markdown stripper (for TTS safety) ────────────────────────────────
_MD_EMPH_RE  = re.compile(r'(?<!\\)([*_])((?:(?!\1).)+?)\1')   # *text* or _text_
_BACKTICK_RE = re.compile(r'(?<!\\)`([^`]+?)`')                # `code`

def strip_inline_markdown(s: str) -> str:
    if not s:
        return s
    s = _MD_EMPH_RE.sub(r"\2", s)
    s = _BACKTICK_RE.sub(r"\1", s)
    return s

# ── Bracket wrappers like <<'Name'>> → Name ──────────────────────────────────
_BRACKET_WRAP_RE = re.compile(r"<<\s*(['\"]?)([^<>]+?)\1\s*>>")
def strip_llm_brackets(text: str) -> str:
    return _BRACKET_WRAP_RE.sub(r"\2", text or "")

# ── Name core pattern (punctuation-agnostic) ─────────────────────────────────
def name_core_regex(name: str) -> Optional[str]:
    if not name:
        return None
    tokens = re.findall(r"\w+", name, flags=re.UNICODE)
    if not tokens:
        return None
    core = r"\W+".join(map(re.escape, tokens))
    return rf"\b({core})\b"

def contains_name(text: str, name: str) -> bool:
    pat = name_core_regex(name)
    return bool(pat and re.search(pat, text, flags=re.IGNORECASE))

def force_exact_casing(text: str, *names: str) -> str:
    out = text
    for name in names:
        pat = name_core_regex(name)
        if pat:
            out = re.compile(pat, flags=re.IGNORECASE).sub(name, out)
    return out

def quote_title_once(text: str, title: str) -> str:
    if title and (title in text) and (f"'{title}'" not in text) and (f"“{title}”" not in text) and (f"\"{title}\"" not in text):
        return text.replace(title, f"'{title}'", 1)
    return text

def rebalance_parens_quotes(s: str) -> str:
    s = re.sub(r"\)\)+", ")", s)
    left, right = s.count("("), s.count(")")
    while right > left and s.rstrip().endswith(")"):
        s = s.rstrip()[:-1]
        right -= 1
    return s

# ── Rank normalization ───────────────────────────────────────────────────────
_NUMBER_RE = re.compile(r"\bnumber\s*[:#-]?\s*(\d+)\b", flags=re.IGNORECASE)

def localize_rank_word(text: str, lang: str) -> str:
    if lang in ("es", "pt-BR"):
        return _NUMBER_RE.sub(r"número \1", text)
    return text

def rank_ok(text: str, rank: int, lang: str) -> bool:
    r = str(rank)
    if lang in ("es", "pt-BR"):
        pats = [
            rf"\bn[úu]mero\s*[:\-]?\s*{r}\b",
            rf"\bn[º°]\.?\s*{r}\b",
            rf"\bno\.?\s*{r}\b",
        ]
        return any(re.search(p, text, re.IGNORECASE) for p in pats)
    return bool(re.search(rf"\bnumber\s*[:\-]?\s*{r}\b", text, re.IGNORECASE))
