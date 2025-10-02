# backend/services/collections_normalize.py
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

ALBUM_IMAGE_KEYS = (
    "album_art_url", "albumArtUrl", "album_artwork", "album_image_url", "albumImageUrl"
)

_CONNECTORS = [
    (r"\s+feat\.\s+", "FEATURED"),
    (r"\s+ft\.\s+", "FEATURED"),
    (r"\s+featuring\s+", "FEATURED"),
    (r"\s+with\s+", "DUET"),
    (r"\s+con\s+", "DUET"),
    (r"\s+y\s+", "DUET"),
    (r"\s+&\s+", "DUET"),
]

def _first(d: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v if not isinstance(v, str) else v.strip()
    return default

def _parse_year(v: Any) -> Optional[int]:
    try:
        y = int(str(v)[:4])
        return y if 1600 <= y <= 2100 else None
    except Exception:
        return None

def to_snake_track(d: dict) -> dict:
    out = {}
    out["track_name"] = d.get("track_name") or d.get("trackName") or d.get("title")
    out["artist_name"] = d.get("artist_name") or d.get("artistName") or d.get("artist")
    out["year_released"] = d.get("year_released") or d.get("yearReleased") or d.get("year")
    out["album_name"] = d.get("album_name") or d.get("albumName")
    out["rank"] = d.get("rank") or d.get("ranking")
    out["mode_flag"] = d.get("mode_flag") or d.get("modeFlag") or ""
    out["mode_flag_detail"] = d.get("mode_flag_detail") or d.get("modeFlagDetail") or ""
    # passthrough
    for k, v in d.items():
        if k not in out:
            out[k] = v
    return out

def normalize_artist_collab(t: dict) -> dict:
    name = (t.get("artist_name") or "").strip()
    if not name:
        return t
    for pattern, mode in _CONNECTORS:
        parts = re.split(pattern, name, flags=re.IGNORECASE)
        if len(parts) >= 2:
            main = parts[0].strip()
            rest = " & ".join(p.strip() for p in parts[1:] if p.strip())
            t["artist_name"] = main
            if not (t.get("mode_flag") or "").strip():
                t["mode_flag"] = mode
            t["featured_artist"] = rest
            return t
    return t

def pick_album_art_url(t: Dict[str, Any]) -> Optional[str]:
    # Prefer any pre-normalized keys first
    for k in ALBUM_IMAGE_KEYS:
        url = t.get(k)
        if isinstance(url, str) and url.strip():
            return url.strip()

    # Flat list of images
    images = t.get("album_images") or t.get("images")
    if isinstance(images, list) and images:
        for img in images:
            if isinstance(img, dict) and isinstance(img.get("url"), str) and img["url"].strip():
                return img["url"].strip()

    # Nested album.images
    album = t.get("album")
    if isinstance(album, dict):
        images = album.get("images")
        if isinstance(images, list) and images:
            for img in images:
                if isinstance(img, dict) and isinstance(img.get("url"), str) and img["url"].strip():
                    return img["url"].strip()
    return None

def coerce_is_explicit(t: Dict[str, Any]) -> bool:
    val = t.get("is_explicit", t.get("explicit", t.get("isExplicit")))
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in {"true", "t", "yes", "y", "1"}: return True
        if s in {"false", "f", "no", "n", "0"}: return False
    return False

def finalize_triplet_fields(tracks: List[Dict[str, Any]]) -> None:
    """Ensure detail/is_explicit/album_artwork present."""
    for t in tracks:
        t["is_explicit"] = coerce_is_explicit(t)
        t["album_artwork"] = pick_album_art_url(t) or None
        if not t.get("detail"):
            t["detail"] = (
                t.get("detail_en")
                or t.get("description")
                or t.get("trackDetail")
                or t.get("track_detail")
                or None
            )

def harmonize_mode_and_feature(t: dict) -> None:
    feat = t.get("featured_artist")
    if not isinstance(feat, str):
        feat = "" if feat is None else str(feat)
    feat = feat.strip()

    flag = (t.get("mode_flag") or "").strip().upper()
    if feat and flag in ("", "SOLO"): t["mode_flag"] = "DUET"
    if not feat and flag == "": t["mode_flag"] = "SOLO"
    if not feat and flag in ("DUET", "FEATURED"): t["mode_flag"] = "SOLO"

    base = t.get("track_name") or ""
    t["track_display_name"] = f"{base} (feat. {feat})" if feat else base
    t["featured_artist"] = feat or None  # normalized or None

def build_artist_display_name(t: dict) -> None:
    main = (t.get("artist_name") or "").strip()
    feat = (t.get("featured_artist") or "").strip()
    if feat and (t.get("mode_flag") or "").upper() == "DUET":
        t["artist_display_name"] = f"{main} and {feat}"
    else:
        t["artist_display_name"] = main
