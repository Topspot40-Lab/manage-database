# backend/services/prompts/text_descriptions.py
from __future__ import annotations

from typing import Dict, Any, Optional, Tuple, List

# Language labels for system messages
_LANG_LABEL = {
    "en": "English",
    "es": "Spanish",
    "pt-BR": "Portuguese (Brazil)",
}

def _lang_label(lang: str) -> str:
    return _LANG_LABEL.get(lang, lang)

def _tts_rules(lang: str, rank: Optional[int]) -> str:
    """
    TTS-friendly constraints. We keep digits in the text;
    your downstream normalizers (ES/PT-BR) can convert as needed.
    """
    if lang == "es":
        rank_hint = f"- If you mention rank, write it as: 'número {rank}'.\n" if rank else ""
    elif lang.lower() in ("pt-br", "ptbr"):
        rank_hint = f"- If you mention rank, write it as: 'número {rank}'.\n" if rank else ""
    else:
        rank_hint = f"- If you mention rank, write it as: 'number {rank}'.\n" if rank else ""

    return (
        "🔊 TTS Formatting (strict):\n"
        "- Do NOT use the '#' character anywhere (e.g., no '#1').\n"
        "- Do NOT use ordinal suffixes (e.g., 1st/2nd/3rd).\n"
        "- No markdown, no emoji.\n"
        f"{rank_hint}"
        "- Keep years and dates as digits (e.g., 1882, 1908)."
    )

def _folk_acoustic_guidance(lang: str) -> str:
    # Genre-specific tone/coverage guidance for Folk Acoustic
    return (
        "🎻 Folk Acoustic – Guidance:\n"
        "- Focus on folk, acoustic, bluegrass, Appalachian/old-time, Celtic/Irish/Scottish/British traditions, "
        "Australian bush ballads, sea shanties, skiffle, and singer-songwriter roots.\n"
        "- Avoid pop/dance framing; keep a roots/heritage tone without romanticized myths or invented lore.\n"
        "- Preserve diacritics (e.g., Seán, Máire) and exact song/artist spellings."
    )

# ─────────────────────────────────────────────────────────────────────────────
# INTRO
# ─────────────────────────────────────────────────────────────────────────────
def build_intro_prompt(
    *,
    track_name: str,
    artist_name: str,
    decade: str,
    genre: str,
    language: str = "en",
    rank: Optional[int] = None,
    words_min: int = 18,
    words_max: int = 30,
    announcer_tone: bool = True,
    folk_acoustic_mode: bool = True,
) -> Dict[str, str]:
    """
    Build a compact intro prompt. Returns dict with 'system' and 'user' strings.
    """
    tl = _lang_label(language)
    tone = "announcer tone, warm and concise" if announcer_tone else "neutral, concise tone"

    tts = _tts_rules(language, rank)
    folk = _folk_acoustic_guidance(language) if folk_acoustic_mode else ""

    system = (
        f"You are a seasoned radio host speaking {tl}. Write tight, hype-but-tasteful intros without adding facts."
    )
    # We keep rank optional; downstream ES/PT will append '(número {rank}).' if missing.
    rank_line = f"- Optional: refer to its chart position as {('número ' if language in ('es','pt-BR','ptbr','pt-br') else 'number ')}{rank}.\n" if rank else ""

    user = (
        f"Song: '{track_name}' by {artist_name}\n"
        f"Decade set: {decade}\n"
        f"Genre context: {genre}\n\n"
        f"Constraints:\n"
        f"- {tone}.\n"
        f"- Exactly 1 sentence; aim for {words_min}–{words_max} words.\n"
        f"- Keep EXACT spellings for song/artist; preserve diacritics.\n"
        f"- Do NOT add or invent facts (no awards, no chart names, no locations unless provided).\n"
        f"{rank_line}"
        f"{tts}\n"
        f"{folk}\n"
        "Return only the sentence, no quotes."
    )

    return {"system": system, "user": user}

# ─────────────────────────────────────────────────────────────────────────────
# DETAIL
# ─────────────────────────────────────────────────────────────────────────────
def build_detail_prompt(
    *,
    track_name: str,
    artist_name: str,
    album_name: Optional[str],
    year_released: Optional[int],
    language: str = "en",
    sentences_min: int = 1,
    sentences_max: int = 3,
    words_min: int = 40,
    words_max: int = 65,
    folk_acoustic_mode: bool = True,
    forbid_new_facts: bool = True,
) -> Dict[str, str]:
    """
    Build a detail (1–3 sentences) prompt. Keeps a factual, evergreen tone.
    """
    tl = _lang_label(language)
    tts = _tts_rules(language, rank=None)
    folk = _folk_acoustic_guidance(language) if folk_acoustic_mode else ""

    system = (
        f"You are a music curator writing in {tl}. Produce compact, evergreen descriptions without hype."
    )

    # Provide only the source facts we want echoed back (to minimize hallucinations).
    facts = [f"Song: {track_name}", f"Artist: {artist_name}"]
    if album_name:
        facts.append(f"Album/session: {album_name}")
    if year_released:
        facts.append(f"Year: {year_released}")
    facts_block = "\n".join(facts)

    no_add = (
        "- Do NOT add or infer any facts beyond what is provided above.\n"
        "- If a detail is unknown, simply omit it.\n"
    ) if forbid_new_facts else (
        "- Prefer widely-known facts; avoid niche/unverifiable claims.\n"
    )

    user = (
        f"{facts_block}\n\n"
        "Write a compact description.\n"
        "Constraints:\n"
        f"- {sentences_min}–{sentences_max} sentences; target {words_min}–{words_max} words total.\n"
        "- Neutral, informed tone; no marketing fluff; no markdown.\n"
        "- Keep EXACT spellings for names; preserve diacritics.\n"
        f"{no_add}"
        f"{tts}\n"
        f"{folk}\n"
        "Return plain text only."
    )

    return {"system": system, "user": user}

# ─────────────────────────────────────────────────────────────────────────────
# ARTIST BIO
# ─────────────────────────────────────────────────────────────────────────────
def build_artist_bio_prompt(
    *,
    artist_name: str,
    language: str = "en",
    sentences_min: int = 1,
    sentences_max: int = 2,
    words_min: int = 25,
    words_max: int = 45,
    folk_acoustic_mode: bool = True,
    forbid_new_facts: bool = True,
) -> Dict[str, str]:
    """
    Build a tight artist bio prompt. Focus on era/scene and relevance
    to folk/acoustic traditions; avoid discography lists.
    """
    tl = _lang_label(language)
    tts = _tts_rules(language, rank=None)
    folk = _folk_acoustic_guidance(language) if folk_acoustic_mode else ""

    system = (
        f"You are a music editor writing in {tl}. Produce concise, evergreen bios."
    )

    no_add = (
        "- Do NOT add or infer facts beyond common, widely-known essentials; omit uncertain claims.\n"
    ) if forbid_new_facts else ""

    user = (
        f"Artist: {artist_name}\n\n"
        "Write a compact bio.\n"
        "Constraints:\n"
        f"- {sentences_min}–{sentences_max} sentences; target {words_min}–{words_max} words.\n"
        "- Emphasize era/scene and significance within folk/acoustic traditions.\n"
        "- No discography lists; no superlatives; no markdown.\n"
        "- Keep EXACT spellings; preserve diacritics.\n"
        f"{no_add}"
        f"{tts}\n"
        f"{folk}\n"
        "Return plain text only."
    )

    return {"system": system, "user": user}

# ─────────────────────────────────────────────────────────────────────────────
# Convenience: build xAI payloads (messages=[])
# ─────────────────────────────────────────────────────────────────────────────
def to_xai_messages(prompt: Dict[str, str]) -> List[Dict[str, str]]:
    """
    Convert {'system':..., 'user':...} to xAI chat-completions messages.
    """
    return [
        {"role": "system", "content": prompt["system"]},
        {"role": "user",   "content": prompt["user"]},
    ]
