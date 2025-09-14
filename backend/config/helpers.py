import os, re
from typing import List

def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1","true","yes","on")

def env_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except ValueError: return default

def env_list(name: str) -> List[str]:
    raw = os.getenv(name, "")
    return [s.strip() for s in raw.split(",") if s.strip()]

def clamp(v: int, lo=0, hi=100) -> int:
    return max(lo, min(hi, v))

def extract_spotify_track_id(value: str | None) -> str | None:
    if not value: return None
    v = value.strip()
    m = re.match(r"^spotify:track:([A-Za-z0-9]{22})$", v) or \
        re.match(r"^https?://open\.spotify\.com/track/([A-Za-z0-9]{22})", v)
    if m: return m.group(1)
    v_no_q = v.split("?", 1)[0]
    return v_no_q if re.fullmatch(r"[A-Za-z0-9]{22}", v_no_q) else None
