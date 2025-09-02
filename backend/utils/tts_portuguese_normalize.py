# backend/utils/tts_portuguese_normalize.py
import re

try:
    from num2words import num2words
except ImportError:
    num2words = None  # fallback if library not installed

def _n2w_pt(n: int) -> str:
    if num2words:
        return num2words(n, lang="pt_BR")
    basics = [
        "zero","um","dois","três","quatro","cinco","seis","sete","oito","nove",
        "dez","onze","doze","treze","catorze","quinze","dezesseis","dezessete",
        "dezoito","dezenove","vinte"
    ]
    return basics[n] if 0 <= n <= 20 else str(n)

def _decade_to_words(n: int) -> str:
    mapping = {
        10: "dez", 20: "vinte", 30: "trinta", 40: "quarenta",
        50: "cinquenta", 60: "sessenta", 70: "setenta",
        80: "oitenta", 90: "noventa"
    }
    return mapping.get(n, str(n))

def normalize_portuguese_tts(text: str) -> str:
    """Convert common digit patterns into natural PT-BR words."""
    s = text
    # número 1 → número um
    s = re.sub(r"\bnúmero\s+(\d+)\b",
               lambda m: f"número {_n2w_pt(int(m.group(1)))}", s, flags=re.I)
    # anos 50 → anos cinquenta
    s = re.sub(r"\banos\s+([1-9]0)\b",
               lambda m: f"anos {_decade_to_words(int(m.group(1)))}", s, flags=re.I)
    return s
