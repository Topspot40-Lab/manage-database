# backend/services/curate.py
from __future__ import annotations
# backend/services/curate.py
from typing import List, Dict, Optional

def curate_tracks_via_xai(theme: str, max_items: int = 45, *, _lang: Optional[str] = None) -> List[Dict]:
    return [{"title": f"{theme} Track {i+1}", "artist": "Unknown", "year": None}
            for i in range(max_items)]
