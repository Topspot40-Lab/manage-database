# backend/services/tts_prep.py
from __future__ import annotations
import re

from backend.services.qafix_es import qa_fix_spanish_intro
from backend.services.locales_common import (
    strip_llm_brackets, strip_inline_markdown,
    force_exact_casing, quote_title_once,
    rebalance_parens_quotes, rank_ok,
)
# ⬇️ NEW: number/decade normalization for Spanish TTS
from backend.utils.tts_spanish_normalize import normalize_spanish_tts


def prepare_for_tts_es(
    text: str,
    *,
    rank: int,
    track_name: str,
    artist_name: str,
    strip_markdown: bool = True,
    number_normalize: bool = True,   # ⬅ flag to toggle normalization
) -> str:
    """
    Deterministic, idempotent cleanup for ES intros before TTS.
    - Runs your QA fixer
    - Strips light markdown
    - Straightens quotes (optional—but helps some voices)
    - Enforces exact song/artist casing + single quoted title
    - Ensures balanced punctuation and final period
    - Guarantees a Spanish rank phrase if rank is provided
    - ✅ Converts ambiguous digits to Spanish words where helpful for TTS
    """
    t = (text or "").strip()
    t = strip_llm_brackets(t)

    # 1) Deterministic fixer (safe to run repeatedly)
    t, _, _ = qa_fix_spanish_intro(
        t, rank=rank, track_name=track_name, artist_name=artist_name
    )

    # 2) TTS-friendly cleanup
    if strip_markdown:
        t = strip_inline_markdown(t)

    # Prefer straight quotes for some TTS engines
    t = t.translate(str.maketrans({
        "“": '"', "”": '"',
        "‘": "'", "’": "'",
    }))

    # 3) Lock exact casing + single quoted title, balance punctuation
    t = force_exact_casing(t, track_name, artist_name)
    t = quote_title_once(t, track_name)
    t = rebalance_parens_quotes(t)

    # 4) Ensure a rank phrase exists (we keep the digit here...)
    if rank and not rank_ok(t, rank, "es"):
        t = f"{t.rstrip('.')} (número {rank})."

    # 5) ...then normalize digits/decades into Spanish words for better TTS
    if number_normalize:
        t = normalize_spanish_tts(t)

    # 6) Final punctuation + whitespace
    if t and t[-1] not in ".!?…":
        t += "."
    t = re.sub(r"\s{2,}", " ", t)

    return t
