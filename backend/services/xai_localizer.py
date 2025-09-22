# backend/services/xai_localizer.py
from typing import Dict, List

def generate_es_pt_json(payload: Dict, languages: List[str]) -> Dict[str, Dict[str, str]]:
    """
    TEMP stub: returns Spanish and Portuguese-BR texts for wiring/testing.
    Replace with your real XAI call later. Expected return shape:
    {
      "es":   {"intro": "...", "detail": "...", "artist_description": "..."},
      "pt-BR":{"intro": "...", "detail": "...", "artist_description": "..."}
    }
    """
    rank   = payload.get("rank")
    decade = payload.get("decade") or ""
    genre  = payload.get("genre") or ""
    track  = payload.get("trackName") or "Track"
    artist = payload.get("artistName") or "Artist"

    out: Dict[str, Dict[str, str]] = {}

    if "es" in languages:
        out["es"] = {
            "intro": f"En el puesto #{rank} de {decade} ({genre}), suena “{track}” de {artist}.",
            "detail": f"Resumen en español: {track} explora un tema clásico con la interpretación de {artist}.",
            "artist_description": f"{artist} es un artista reconocido; descripción breve en español.",
        }

    if "pt-BR" in languages or "pt" in languages:
        out["pt-BR"] = {
            "intro": f"No #{rank} de {decade} ({genre}), toca “{track}” de {artist}.",
            "detail": f"Resumo em português: {track} aborda um tema clássico com a interpretação de {artist}.",
            "artist_description": f"{artist} é um artista reconhecido; descrição breve em português.",
        }

    return out
