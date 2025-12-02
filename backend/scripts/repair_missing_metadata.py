# backend/scripts/repair_missing_metadata.py
from __future__ import annotations
import os
import logging
from pathlib import Path

import httpx
from dotenv import load_dotenv
from supabase import create_client
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

print("🚀 repair_missing_metadata.py STARTED")

# ───────────────────────────────────────────────
# Load .env from project root
# ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

print(f"📄 Loading environment from: {ENV_FILE}")
load_dotenv(ENV_FILE)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

print("🔧 ENV CHECK:")
print(f"  SUPABASE_URL = {SUPABASE_URL}")
print(f"  SUPABASE_SERVICE_ROLE_KEY = {'SET' if SUPABASE_SERVICE_ROLE_KEY else 'MISSING'}")
print(f"  SPOTIFY_CLIENT_ID = {SPOTIFY_CLIENT_ID}")
print(f"  SPOTIFY_CLIENT_SECRET = {'SET' if SPOTIFY_CLIENT_SECRET else 'MISSING'}")
print("🔧 Running metadata repair...\n")

logger = logging.getLogger("repair")
logging.basicConfig(level=logging.INFO)

# ───────────────────────────────────────────────
# Initialize Supabase + Spotify
# ───────────────────────────────────────────────
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    spotify = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
    )
else:
    print("❌ Spotify credentials missing — cannot repair album_artwork/duration/popularity.\n")


# ───────────────────────────────────────────────
# Low-level REST fetch using HTTP Range
# ───────────────────────────────────────────────
def fetch_range(start: int, end: int):
    """Fetch a range of rows from Supabase using HTTP Range headers."""
    url = f"{SUPABASE_URL}/rest/v1/track?select=*"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Range": f"{start}-{end}"
    }

    r = httpx.get(url, headers=headers, timeout=30.0)
    if r.status_code not in (200, 206):
        raise RuntimeError(f"Supabase HTTP {r.status_code}: {r.text}")

    return r.json()


# ───────────────────────────────────────────────
# Main repair function
# ───────────────────────────────────────────────
def repair_missing_metadata():
    print("🎨 Starting metadata repair…\n")

    # Pagination setup
    all_rows = []
    page_size = 1000
    offset = 0

    # ───────────────────────────────────────────────
    # Fetch all rows using Range pagination
    # ───────────────────────────────────────────────
    while True:
        start = offset
        end = offset + page_size - 1

        print(f"📥 Requesting rows {start}–{end}…")
        chunk = fetch_range(start, end)

        if not chunk:
            break

        print(f"   → Loaded {len(chunk)} rows.")
        all_rows.extend(chunk)

        if len(chunk) < page_size:
            break

        offset += page_size

    print(f"\n🔍 Total loaded rows: {len(all_rows)}\n")

    updated = 0
    skipped_no_id = 0
    skipped_complete = 0
    failures = 0

    # ───────────────────────────────────────────────
    # Process rows
    # ───────────────────────────────────────────────
    for row in all_rows:
        track_id = row.get("spotify_track_id")

        if not track_id:
            skipped_no_id += 1
            continue

        # Skip fully valid rows
        if (
            row.get("album_artwork") and
            row.get("duration_ms") and
            row.get("popularity") is not None
        ):
            skipped_complete += 1
            continue

        print(f"➡️ Fetching Spotify metadata for {track_id}…")

        try:
            sp = spotify.track(track_id)

            artwork = (
                sp.get("album", {})
                .get("images", [{}])[0]
                .get("url")
            )

            duration_ms = sp.get("duration_ms")
            popularity = sp.get("popularity")

            supabase.table("track").update(
                {
                    "album_artwork": artwork,
                    "duration_ms": duration_ms,
                    "popularity": popularity,
                }
            ).eq("id", row["id"]).execute()

            updated += 1

        except Exception as e:
            print(f"❌ Spotify error for {track_id}: {e}")
            failures += 1

    # ───────────────────────────────────────────────
    # Summary
    # ───────────────────────────────────────────────
    print("\n📊 Summary:")
    print(f"   ✅ Updated rows:           {updated}")
    print(f"   ➖ Skipped (no Spotify ID): {skipped_no_id}")
    print(f"   ➖ Skipped (already full):  {skipped_complete}")
    print(f"   ❌ Spotify failures:        {failures}")


# ───────────────────────────────────────────────
# Run script
# ───────────────────────────────────────────────
if __name__ == "__main__":
    repair_missing_metadata()
    print("\n🎉 repair_missing_metadata.py FINISHED")
