import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.spotify_service import handle_missing_track, reassign_ranks


with open("backend/data/test/test_topspot_input.json", "r", encoding="utf-8") as f:
    data = json.load(f)

tracks = data["tracks"]
spares = data["spares"]

# 🔍 Fix broken tracks interactively
for track in tracks[:]:
    if not track.get("spotify_track_id"):
        handle_missing_track(track, tracks, spares)

# 🧼 Remove invalid
tracks = [t for t in tracks if t.get("spotify_track_id")]

# 🧩 Top 40 guarantee (in this test, 3 target tracks total)
while len(tracks) < 3 and spares:
    spare = spares.pop(0)
    spare["rank"] = len(tracks) + 1
    tracks.append(spare)

reassign_ranks(tracks)

# ✅ Write test result
with open("backend/data/test/test_topspot_output.json", "w", encoding="utf-8") as f:
    json.dump({"tracks": tracks}, f, indent=2)

print("\n🎉 Test completed. Output written to data/test/test_topspot_output.json")
