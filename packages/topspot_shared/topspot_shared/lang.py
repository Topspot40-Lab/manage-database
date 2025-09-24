# packages/topspot_shared/topspot_shared/lang.py
from __future__ import annotations
from typing import Literal

Lang = Literal["en", "es", "pt-BR"]

# Accept common aliases; return canonical short code used on the wire.
_ALIAS = {
    # English
    "en": "en", "english": "en",

    # Spanish
    "es": "es", "spanish": "es", "español": "es", "espanol": "es", "sp": "es", "es-mx": "es",

    # Portuguese (Brazil) – canonical is pt-BR
    "pt": "pt-BR", "ptbr": "pt-BR", "pt-br": "pt-BR",
    "portuguese": "pt-BR", "português": "pt-BR", "portugues": "pt-BR",
}

def canon_lang(s: str | None) -> Lang:
    if not s:
        return "en"
    return _ALIAS.get(s.strip().lower(), "en")  # default "en"
