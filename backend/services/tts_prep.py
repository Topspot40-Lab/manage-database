# backend/services/tts_prep.py
from __future__ import annotations
import re

from backend.services.qafix_es import qa_fix_spanish_intro
from backend.services.locales_common import (
    strip_llm_brackets, strip_inline_markdown,
    force_exact_casing, quote_title_once,
    rebalance_parens_quotes, rank_ok,
)
# ⬇️ number/decade normalization for Spanish TTS (your existing normalizer)
from backend.utils.tts_spanish_normalize import normalize_spanish_tts
from backend.utils.tts_portuguese_normalize import normalize_portuguese_tts


# ─────────────────────────────────────────────────────────────────────────────
# Spanish year handling + small guards for repeated phrases
# ─────────────────────────────────────────────────────────────────────────────
_UNITS = ["cero","uno","dos","tres","cuatro","cinco","seis","siete","ocho","nueve"]
_TEENS = ["diez","once","doce","trece","catorce","quince","dieciséis",
          "diecisiete","dieciocho","diecinueve"]
_TENS  = ["", "", "veinte","treinta","cuarenta","cincuenta",
          "sesenta","setenta","ochenta","noventa"]
_HUNDS = ["","ciento","doscientos","trescientos","cuatrocientos",
          "quinientos","seiscientos","setecientos","ochocientos","novecientos"]

def _spell_1_99_es(n: int) -> str:
    if n < 10:
        return _UNITS[n]
    if n < 20:
        return _TEENS[n-10]
    d, u = divmod(n, 10)
    if n == 20:
        return "veinte"
    if d == 2 and u > 0:  # 21..29
        return "veinti" + ("uno" if u == 1 else _UNITS[u])
    return _TENS[d] if u == 0 else f"{_TENS[d]} y {_UNITS[u]}"

def _spell_100_999_es(n: int) -> str:
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    if c == 0:
        return _spell_1_99_es(r)
    head = _HUNDS[c]
    return head if r == 0 else f"{head} {_spell_1_99_es(r)}"

def _spell_year_es(n: int) -> str:
    # Natural Spanish phrasing for 1000–2099
    if 1000 <= n <= 1999:
        r = n - 1000
        return "mil" if r == 0 else f"mil {_spell_100_999_es(r)}"
    if 2000 <= n <= 2099:
        r = n - 2000
        return "dos mil" if r == 0 else f"dos mil {_spell_1_99_es(r) if r < 100 else _spell_100_999_es(r)}"
    return str(n)

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")

def _mask_years(s: str):
    """Replace years with tokens to protect them during other normalizations."""
    mapping: dict[str, int] = {}
    def repl(m):
        y = m.group(1)
        tok = f"__YEAR_{y}__"
        mapping[tok] = int(y)
        return tok
    return _YEAR_RE.sub(repl, s), mapping

def _restore_years_spelled(s: str, mapping: dict[str, int]) -> str:
    for tok, year in mapping.items():
        s = s.replace(tok, _spell_year_es(year))
    return s

def _restore_years_prefixed(s: str, mapping: dict[str, int]) -> str:
    # Keep numerals but nudge Spanish prosody with "año 1882"
    for tok, year in mapping.items():
        s = s.replace(tok, f"año {year}")
    return s

def _restore_years_literal(s: str, mapping: dict[str, int]) -> str:
    for tok, year in mapping.items():
        s = s.replace(tok, str(year))
    return s

# collapse accidental repeats like "número cero número cero"
_DUP_NUMERO_CERO_RE = re.compile(r"(?i)\b(número\s+cero)(?:\s+\1)+\b")
def _dedupe_numero_cero(s: str) -> str:
    return _DUP_NUMERO_CERO_RE.sub(r"\1", s)


# ─────────────────────────────────────────────────────────────────────────────
# ES + PT-BR preparation
# ─────────────────────────────────────────────────────────────────────────────
def prepare_for_tts_es(
    text: str,
    *,
    rank: int | None,
    track_name: str,
    artist_name: str,
    strip_markdown: bool = True,
    number_normalize: bool = True,
    # NEW knobs (safe defaults so existing calls keep working):
    spell_years: bool = True,        # True → "1882" -> "mil ochocientos ochenta y dos"
    prefer_numerals: bool = False,   # True → keep digits but prefix "año 1882"
) -> str:
    """
    Deterministic, idempotent cleanup for Spanish text before TTS.
    Also makes Turbo v2.5 speak years in Spanish (by default spells out 4-digit years).
    """
    t = (text or "").strip()
    t = strip_llm_brackets(t)

    # 1) Deterministic fixer (safe to run repeatedly)
    if rank is not None:
        t, _, _ = qa_fix_spanish_intro(
            t, rank=rank, track_name=track_name, artist_name=artist_name
        )

    # 2) TTS-friendly cleanup
    if strip_markdown:
        t = strip_inline_markdown(t)
    # prefer straight quotes for some TTS engines
    t = t.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))

    # 3) Lock exact casing + single quoted title, balance punctuation
    t = force_exact_casing(t, track_name, artist_name)
    t = quote_title_once(t, track_name)
    t = rebalance_parens_quotes(t)

    # 4) Ensure a rank phrase exists (digit kept here; later normalized)
    if rank and not rank_ok(t, rank, "es"):
        t = f"{t.rstrip('.')} (número {rank})."

    # 5) Protect 4-digit years, run your normalizer, then restore years
    t, year_map = _mask_years(t)
    if number_normalize:
        t = normalize_spanish_tts(t)  # your existing number/decade normalizer

    if spell_years and not prefer_numerals:
        t = _restore_years_spelled(t, year_map)     # "mil ochocientos..."
    elif prefer_numerals:
        t = _restore_years_prefixed(t, year_map)    # "año 1882"
    else:
        t = _restore_years_literal(t, year_map)     # just digits

    # 6) Final polish: protect names, tone, dedupe, punctuation
    t = force_exact_casing(t, track_name, artist_name)  # re-assert casing after ops
    # (if you have any tone polish helper for ES, call it here)
    t = _dedupe_numero_cero(t)

    if t and t[-1] not in ".!?…":
        t += "."
    t = re.sub(r"\s{2,}", " ", t)
    return t


def prepare_for_tts_pt_br(
    text: str,
    *,
    rank: int | None,
    track_name: str,
    artist_name: str,
    strip_markdown: bool = True,
    number_normalize: bool = True,
) -> str:
    """
    Deterministic cleanup for PT-BR before TTS.
    Similar to ES but uses Portuguese normalization.
    """
    t = (text or "").strip()

    if strip_markdown:
        t = strip_inline_markdown(t)

    # straight quotes
    t = t.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))

    # lock casing, quotes, punctuation
    t = force_exact_casing(t, track_name, artist_name)
    t = quote_title_once(t, track_name)
    t = rebalance_parens_quotes(t)

    if number_normalize:
        t = normalize_portuguese_tts(t)

    if t and t[-1] not in ".!?…":
        t += "."
    return t
