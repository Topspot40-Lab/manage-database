from __future__ import annotations
from typing import List, Dict, Any, Tuple
import logging

log = logging.getLogger("collections_utils")

def build_ranking_from_tracks(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    If your curated/enriched tracks each have a 'rank' and 'track_id' (or spotify_track_id),
    build a ranking array. Prefer DB track_id; fallback to spotify_track_id.
    """
    ranking = []
    for t in tracks:
        r = t.get("rank")
        if r is None:
            continue
        ranking.append({
            "rank": int(r),
            "track_id": t.get("track_id"),  # may be None if you haven’t resolved DB ids yet
            "spotify_track_id": t.get("spotify_track_id")
        })
    # sort, unique by rank, keep the first occurrence
    seen = set()
    deduped = []
    for row in sorted(ranking, key=lambda x: x["rank"]):
        if row["rank"] in seen:
            continue
        seen.add(row["rank"])
        deduped.append(row)
    return deduped

def validate_compact_ranks(ranking: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Ensure ranks are 1..N contiguous (no gaps/dups). Return (ok, msg).
    """
    if not ranking:
        return True, "empty ranking ok"
    vals = sorted({int(r["rank"]) for r in ranking if r.get("rank") is not None})
    if vals[0] != 1:
        return False, f"ranks must start at 1 (got {vals[0]})"
    if vals != list(range(1, len(vals)+1)):
        return False, f"ranks must be 1..N with no gaps/dups (got {vals})"
    return True, "ok"
