# backend/services/ads/script_generator.py
from __future__ import annotations
import re
import random
from dataclasses import dataclass
from typing import Optional, Dict

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

CTA_LINES = [
    "Tap now to keep the countdown going.",
    "Tap to hear the next story and song.",
    "Tap to relive the hits you love—track by track.",
    "Tap now and let TopSpot bring your music alive.",
]

HOOK_LINES = [
    "With TopSpot, the music you love comes alive.",
    "TopSpot brings back the stories behind the songs.",
    "Your personal countdown to the classics starts here.",
    "Pick your decade and genre—then let the memories roll.",
]

SFX_OPENERS = [
    "[Sound: record-player needle drop]",
    "[Sound: retro radio dial + static]",
    "[Sound: vinyl crackle, soft fade-in]",
]

SFX_CLOSERS = [
    "[Sound: quick music sting, fade out]",
    "[Sound: radio click-off]",
]

@dataclass
class TrackAdInputs:
    # Required-ish core
    track_title: str
    artist_name: str
    # Either '1960s' or numeric like 1965—both okay
    year_released: Optional[str] = None
    # High-level context
    category: Optional[str] = None   # e.g., "1960s"
    genre: Optional[str] = None      # e.g., "Motown"
    # Your generated copy
    intro_text: Optional[str] = None
    detail_text: Optional[str] = None
    # Optional rank for countdown flavor
    rank: Optional[int] = None
    # Language hint (not used heavily here, but future-proof)
    language: str = "en"

def _first_n_sentences(text: str, n: int = 2) -> str:
    parts = SENTENCE_SPLIT.split(text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:n])

def _sanitize(s: Optional[str]) -> str:
    return (s or "").strip()

def _fallback_intro(inputs: TrackAdInputs) -> str:
    # If no intro provided, build one that matches your countdown vibe
    bits = []
    if inputs.rank is not None and inputs.category:
        bits.append(f"At number {inputs.rank} in our {inputs.category} {inputs.genre or ''} countdown")
    elif inputs.category or inputs.genre:
        bits.append(f"In our {inputs.category or ''} {inputs.genre or ''} picks")
    else:
        bits.append("On TopSpot today")
    bits = [b.strip() for b in bits if b.strip()]
    prefix = ", ".join(bits) if bits else "On TopSpot"
    return f"{prefix}, it’s “{inputs.track_title}” by {inputs.artist_name}."

def _short_detail(detail_text: Optional[str]) -> str:
    if not detail_text:
        return ""
    return _first_n_sentences(detail_text, n=2)

def estimate_spoken_seconds(text: str, wpm: int = 155) -> int:
    # Rough time check (Spotify 30s target). Oldies audiences often prefer a slightly slower pace.
    words = len(re.findall(r"\w+", text))
    seconds = int(round((words / wpm) * 60))
    return seconds

def generate_ad_script(inputs: TrackAdInputs, *, seed: Optional[int] = None) -> Dict[str, str]:
    """
    Returns a dict with:
      - 'script': the full ad script (≈30s)
      - 'estimated_seconds': int
      - 'notes': guidance if long/short
    """
    if seed is not None:
        random.seed(seed)

    opener = random.choice(SFX_OPENERS)
    hook = random.choice(HOOK_LINES)

    intro = _sanitize(inputs.intro_text) or _fallback_intro(inputs)
    detail = _short_detail(_sanitize(inputs.detail_text))

    cta = random.choice(CTA_LINES)
    closer = random.choice(SFX_CLOSERS)

    # Optional decade/genre tag line (subtle reinforcement)
    tag = ""
    if inputs.category or inputs.genre:
        c = inputs.category or ""
        g = inputs.genre or ""
        tag = f"Pick your decade and genre—{c} {g}".strip().replace("  ", " ")
        tag = tag.strip("- ").strip()

    # Assemble script in a pacing-friendly order
    parts = [
        f"{opener}",
        f"{hook}",
        intro,
        detail if detail else "",
        (f"{tag}." if tag else ""),
        cta,
        f"{closer}",
    ]
    # Clean empties and join
    script = " ".join(p for p in parts if p)

    secs = estimate_spoken_seconds(script, wpm=150)  # a hair slower = warmer delivery
    notes = ""
    if secs > 33:
        notes = "⚠️ This reads a bit long for 30s. Trim a sentence from the detail or tighten your hook."
    elif secs < 22:
        notes = "ℹ️ Slightly short. Consider adding one more detail sentence or a stronger CTA."

    return {
        "script": script,
        "estimated_seconds": str(secs),
        "notes": notes,
    }
