import os
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

LANGUAGE_BUCKETS = {"en":"audio-en", "es":"audio-es", "pt-BR":"audio-ptbr"}
BUCKETS = {lang: {"intro": b, "detail": b, "artist": b} for lang, b in LANGUAGE_BUCKETS.items()}
AUDIO_PREFIXES = {"intro":"intro", "detail":"detail", "artist":"artist"}

# Legacy
BUCKET_TRACK_INTRO   = "track-intro-mp3-files"
BUCKET_TRACK_DETAIL  = "track-detail-mp3-files"
BUCKET_ARTIST        = "artist-mp3-files"
BUCKET_SPOTIFY_TRACK = "spotify-track-mp3-files"
SUPABASE_BUCKET_ARTIST_MP3 = BUCKETS["en"]["artist"]
