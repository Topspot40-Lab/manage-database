# backend/services/collection_import/meta_utils.py
from __future__ import annotations
from typing import Any, Dict

from backend.services.collection_import.normalizers import (
    coerce_bool,
    REPAIR_KEYS as BASE_REPAIR_KEYS,
)

# ─────────────── Config ───────────────
PROTECTED_FILL_ONLY = {"detail"}  # never overwrite these
REPAIR_KEYS = set(BASE_REPAIR_KEYS) | {
    "source_type", "source_title", "years_on_air", "source_role", "version_notes"
}


# ─────────────── Utility Functions ───────────────
def _is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) == 0
    return False


def _pick_first(*vals):
    for v in vals:
        if v is not None and not _is_missing(v):
            return v
    return None


# ─────────────── Metadata Helpers ───────────────
def _augment_meta_with_source_fields(meta: Dict[str, Any] | None, item: Dict[str, Any] | None) -> Dict[str, Any]:
    """Normalize source_* fields for TV or Theme-style imports."""
    meta = dict(meta or {})
    item = item or {}

    source_title = _pick_first(
        item.get("source_title"), meta.get("source_title"),
        item.get("show_name"), meta.get("show_name"),
    )
    if source_title:
        meta["source_title"] = source_title

    years_on_air = _pick_first(
        item.get("years_on_air"), meta.get("years_on_air"),
        item.get("year_on_air"), meta.get("year_on_air"),
        item.get("yearOnAir"), meta.get("yearOnAir"),
    )
    if years_on_air:
        meta["years_on_air"] = years_on_air

    source_role = _pick_first(
        item.get("source_role"), meta.get("source_role"),
        item.get("show_genre"), meta.get("show_genre"),
    )
    if source_role:
        meta["source_role"] = source_role

    source_type = _pick_first(item.get("source_type"), meta.get("source_type"))
    if not source_type:
        looks_like_tv = bool(
            source_title or years_on_air or source_role
            or str(item.get("genre", "")).lower() in {"tv themes", "tv", "tv-theme", "tv theme"}
        )
        if looks_like_tv:
            source_type = "TV"
    if source_type:
        meta["source_type"] = source_type

    return meta


def _apply_json_track_meta(t, meta: Dict[str, Any], prefer_json: bool) -> Dict[str, Any]:
    """Apply JSON metadata to an existing Track safely."""
    changes = {}
    for k in REPAIR_KEYS:
        if k not in meta:
            continue

        # ✅ skip if Track model doesn't have this field
        if not hasattr(t, k):
            continue

        incoming = meta[k]
        if k == "is_explicit":
            incoming = coerce_bool(incoming)

        current = getattr(t, k, None)

        # Never overwrite protected fields
        if k in PROTECTED_FILL_ONLY:
            if _is_missing(current) and not _is_missing(incoming):
                setattr(t, k, incoming)
                changes[k] = incoming
            continue

        # Overwrite logic
        if prefer_json:
            if not _is_missing(incoming) and incoming != current:
                setattr(t, k, incoming)
                changes[k] = incoming
        else:
            if _is_missing(current) and not _is_missing(incoming):
                setattr(t, k, incoming)
                changes[k] = incoming
    return changes
