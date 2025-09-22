# backend/utils/datetime_utils.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

def ensure_aware_utc(dt: datetime | None) -> Optional[datetime]:
    """Return a timezone-aware UTC datetime (or None if input is None)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def parse_dt_utc(val) -> Optional[datetime]:
    """
    Parse ISO-ish strings (handles 'Z') or passthrough datetime, return aware UTC dt or None.
    """
    if not val:
        return None
    if isinstance(val, datetime):
        return ensure_aware_utc(val)
    try:
        # tolerate trailing 'Z'
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return ensure_aware_utc(dt)
    except Exception:
        return None

def utcnow_iso_seconds() -> str:
    """UTC now as ISO 8601 with seconds precision and timezone info."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
