# backend/state.py
import asyncio

# Stores the most recently loaded decade + genre from Supabase
current_decade_genre = {
    "decade": None,
    "genre": None
}

# 👇 New: signal used to skip the currently playing track
skip_event = asyncio.Event()
