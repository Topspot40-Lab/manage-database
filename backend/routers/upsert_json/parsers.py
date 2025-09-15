from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

def _norm(s: str | None) -> str:
    return (s or "").strip()

def _as_list(x) -> list:
    if not x:
        return []
    if isinstance(x, list):
        return x
    return [x]

@dataclass
class RootPayload:
    decade_name: str
    genre_name: str
    artists: List[Dict[str, Any]]
    tracks: List[Dict[str, Any]]
    rankings: List[Dict[str, Any]]

def normalize_root_payload(data: Any, *, fallback_decade: str, fallback_genre: str) -> RootPayload:
    """
    Accepts the raw JSON (dict or list) and outputs a normalized object.
    """
    if isinstance(data, list):
        # legacy: a bare ranking list
        data = {"track_ranking": data}

    decade_name = _norm(data.get("category")) or fallback_decade
    genre_name = _norm(data.get("genre")) or fallback_genre

    artists = _as_list(data.get("artist") or [])
    tracks = _as_list(data.get("track") or [])
    rankings = _as_list(data.get("track_ranking") or [])

    return RootPayload(
        decade_name=decade_name,
        genre_name=genre_name,
        artists=artists,
        tracks=tracks,
        rankings=rankings,
    )
