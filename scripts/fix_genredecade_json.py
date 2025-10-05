#!/usr/bin/env python3
from __future__ import annotations
import json, sys, argparse
from pathlib import Path
from typing import Any, Dict, List

# minimal mojibake repair map (extend when you see new sequences)
REMAP = {
    "Ã¢â‚¬â€œ": "–",  # en dash
    "Ã¢â‚¬â€": "—",  # em dash
    "Ã¢â‚¬â„¢": "’",  # right single quote
    "Ã¢â‚¬Ëœ": "‘",  # left single quote
    "ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“": "‘",
    "ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢": "’",
    "Ã¢â‚¬Å“": "“",
    "Ã¢â‚¬Â": "”",
    "Ã¢â‚¬Â¦": "…",
}

def de_mojibake(s: str | None) -> str | None:
    if not isinstance(s, str):
        return s
    out = s
    for bad, good in REMAP.items():
        out = out.replace(bad, good)
    return out

def clean_strings(obj: Any) -> Any:
    """Recursively de-mojibake all strings in dict/list structures."""
    if isinstance(obj, dict):
        return {k: clean_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_strings(v) for v in obj]
    if isinstance(obj, str):
        return de_mojibake(obj)
    return obj

def main():
    p = argparse.ArgumentParser(description="Fix mojibake + fill artist fields in genre/decade JSON.")
    p.add_argument("--in", dest="inp", required=True, help="Input JSON path")
    p.add_argument("--out", dest="outp", help="Output JSON path (defaults to <input>.fixed.json)")
    p.add_argument("--fallback-name", default="TV Hits", help="Fallback artist name when blank")
    p.add_argument("--fallback-spid", default="24DQLSng7bKZD4GXLIaQbv", help="Fallback Spotify artist ID")
    args = p.parse_args()

    IN = Path(args.inp)
    OUT = Path(args.outp) if args.outp else IN.with_name(IN.stem + ".fixed.json")

    if not IN.exists():
        print(f"File not found: {IN}", file=sys.stderr)
        sys.exit(1)

    doc = json.loads(IN.read_text(encoding="utf-8"))

    # 1) De-mojibake everything
    doc = clean_strings(doc)

    # 2) Build artist maps (if file has an 'artist' array)
    artists = doc.get("artist") or []
    name_to_canon: Dict[str, str] = {}
    name_to_spid: Dict[str, str] = {}

    for a in artists:
        n = (a.get("artist_name") or "").strip()
        sp = (a.get("spotify_artist_id") or "").strip() or None
        if n:
            name_to_canon[n.lower()] = n
            if sp:
                name_to_spid[n.lower()] = sp

    # Ensure fallback exists in artist map
    if args.fallback_name.lower() not in name_to_canon:
        artists.append({
            "artist_name": args.fallback_name,
            "spotify_artist_id": args.fallback_spid,
            "artist_artwork": None,
            "artist_description": "Studio project specializing in faithful re-recordings of classic TV themes.",
            "not_on_spotify": False,
        })
        name_to_canon[args.fallback_name.lower()] = args.fallback_name
        name_to_spid[args.fallback_name.lower()] = args.fallback_spid
        doc["artist"] = artists  # ensure it’s written back

    # 3) Locate track-like lists
    tracklists: List[List[Dict[str, Any]]] = []
    for key in ("track", "tracks", "track_ranking"):
        val = doc.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            tracklists.append(val)

    # Heuristic fallback: any other list of dicts with 'rank' or 'ranking'
    if not tracklists:
        for v in doc.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and ("rank" in v[0] or "ranking" in v[0]):
                tracklists.append(v)

    fixed_blank_artists = 0
    filled_spids = 0

    for lst in tracklists:
        for t in lst:
            raw_name = (t.get("artist_name") or "").strip()
            disp_name = (t.get("artist_display_name") or "").strip()

            if not raw_name:
                # Use fallback
                t["artist_name"] = args.fallback_name
                t["artist_display_name"] = disp_name or args.fallback_name
                if not t.get("spotify_artist_id"):
                    t["spotify_artist_id"] = args.fallback_spid
                fixed_blank_artists += 1
            else:
                canon = name_to_canon.get(raw_name.lower()) or raw_name
                t["artist_name"] = canon
                t["artist_display_name"] = disp_name or canon
                if not t.get("spotify_artist_id"):
                    spid = name_to_spid.get(raw_name.lower())
                    if spid:
                        t["spotify_artist_id"] = spid
                        filled_spids += 1

    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✔ Wrote {OUT}")
    print(f"   - tracks with blank artist filled: {fixed_blank_artists}")
    print(f"   - tracks with missing spotify_artist_id filled: {filled_spids}")

if __name__ == "__main__":
    main()
