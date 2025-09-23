def format_ms(ms: int | None) -> str:
    if ms is None: return ""
    s = ms // 1000
    h, r = divmod(s, 3600); m, s = divmod(r, 60)
    return f"{m:02d}:{s:02d}" if h == 0 else f"{h:d}:{m:02d}:{s:02d}"

def plan_tts_simple(mode: str, first_vocal_ms: int | None,
                    latency_ms: int = 750, guard_ms: int = 1000) -> bool:
    # True => overlay on track; False => play bed first
    if mode == "intro": return True
    if first_vocal_ms is None: return False
    window = max(0, first_vocal_ms - latency_ms - guard_ms)
    return window >= 40_000
