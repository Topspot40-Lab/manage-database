# backend/utils/tts_spanish_normalize.py
import re
from typing import Optional

try:
    from num2words import num2words
except ImportError:
    num2words = None  # graceful fallback

def _n2w_es(n: int) -> str:
    if num2words:
        return num2words(n, lang="es")
    basics = ["cero","uno","dos","tres","cuatro","cinco","seis","siete","ocho","nueve",
              "diez","once","doce","trece","catorce","quince","dieciséis","diecisiete",
              "dieciocho","diecinueve","veinte"]
    return basics[n] if 0 <= n <= 20 else str(n)

def _ordinal_es(n: int) -> str:
    if num2words:
        return num2words(n, lang="es", to="ordinal")
    return _n2w_es(n)

def _decade_to_words(n: int) -> str:
    mapping = {
        10: "diez", 20: "veinte", 30: "treinta", 40: "cuarenta",
        50: "cincuenta", 60: "sesenta", 70: "setenta",
        80: "ochenta", 90: "noventa"
    }
    return mapping.get(n, str(n))

def normalize_spanish_tts(text: str) -> str:
    """
    Normalize digits to Spanish words where it helps TTS:
    - "#1", "No. 1", "Nº 1" → "número uno"
    - "número 1" → "número uno"
    - "Top 5" → "los cinco mejores"
    - Ordinals: "1.º/1er/1ª" → "primero/primera" (approx.)
    - Decades: "años 50", "los 70s", "1950s" → "años cincuenta / setenta"
    - Standalone small numbers (0–20) → words (conservative)
    """
    s = text

    # Rankings like "#1", "No. 1", "Nº 1"
    s = re.sub(r"(?:#|N[ºo]\.?|No\.)\s*(\d+)",
               lambda m: f"número {_n2w_es(int(m.group(1)))}",
               s, flags=re.IGNORECASE)

    # "número 1" → "número uno"
    s = re.sub(r"\bnúmero\s+(\d+)\b",
               lambda m: f"número {_n2w_es(int(m.group(1)))}",
               s, flags=re.IGNORECASE)

    # "Top 5" → "los cinco mejores"
    s = re.sub(r"\bTop\s+(\d+)\b",
               lambda m: f"los {_n2w_es(int(m.group(1)))} mejores",
               s, flags=re.IGNORECASE)

    # Ordinals (simple)
    s = re.sub(r"\b(\d+)\s?(?:º|o\.|er|er\.|a\.|ª)\b",
               lambda m: _ordinal_es(int(m.group(1))), s, flags=re.IGNORECASE)

    # Decades
    s = re.sub(r"\baños\s+([1-9]0)\b",
               lambda m: f"años {_decade_to_words(int(m.group(1)))}",
               s, flags=re.IGNORECASE)
    s = re.sub(r"\blos\s+([1-9]0)s\b",
               lambda m: f"los {_decade_to_words(int(m.group(1)))}",
               s, flags=re.IGNORECASE)
    s = re.sub(r"\b(19|20)([1-9]0)s\b",
               lambda m: f"años {_decade_to_words(int(m.group(2)))}", s)

    # Small standalone numbers 0–20 → words (avoid touching years/durations patterns)
    def _small_num(m):
        n = int(m.group(0))
        return _n2w_es(n) if 0 <= n <= 20 else m.group(0)
    s = re.sub(r"\b([0-9]|1[0-9]|20)\b", _small_num, s)

    return s
