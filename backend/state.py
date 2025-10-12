# backend/state.py
import asyncio

# ─────────────────────────────────────────────
# Currently loaded decade/genre context
# ─────────────────────────────────────────────
current_decade_genre = {
    "decade": None,
    "genre": None,
    "lang": "en",   # keep the last selected language here too
}

# ─────────────────────────────────────────────
# Currently loaded collection context
# ─────────────────────────────────────────────
current_collection = {
    "collection": None,
    "lang": "en",
}

# ─────────────────────────────────────────────
# Global async signal to skip the currently playing track
# (matches your async playback flow)
# ─────────────────────────────────────────────
skip_event = asyncio.Event()
