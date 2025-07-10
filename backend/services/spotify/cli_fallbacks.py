from typing import Dict, List, Optional

def prompt_user_for_replacement(track_name: str, artist_name: str, suggestions: List[Dict], spare_tracks: Optional[List[Dict]] = None) -> Optional[Dict]:
    print(f"\n🎯 Missing track: '{track_name}' by {artist_name}")
    for idx, s in enumerate(suggestions, 1):
        print(f"[{idx}] {s['trackName']} – {s['artistName']} ({s['yearReleased']}) | Pop: {s['popularity']}")
    if spare_tracks:
        print("\n🎵 Spare Tracks:")
        for s_idx, s in enumerate(spare_tracks, 1):
            print(f"[S{s_idx}] {s['trackName']} – {s['artistName']} ({s['yearReleased']})")
    print("[s] Skip this track")

    while True:
        choice = input(f"📝 Choose [1–{len(suggestions)}] | [S#] | [s]: ").strip().lower()
        if choice == "s":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(suggestions):
            return suggestions[int(choice) - 1]
        if choice.startswith("s") and choice[1:].isdigit():
            idx = int(choice[1:]) - 1
            if spare_tracks and 0 <= idx < len(spare_tracks):
                return spare_tracks[idx]
        print("❗ Invalid input.")

def choose_spare_track(spare_tracks: List[Dict]) -> Optional[Dict]:
    """Prompt the user to pick a spare track from a list."""
    print("\n🎒 Spare Tracks:")
    for idx, t in enumerate(spare_tracks, 1):
        print(f"[{idx}] {t['trackName']} by {t['artistName']} (Pop: {t.get('popularity', 'N/A')})")
    print("[s] Skip")

    while True:
        choice = input(f"Pick spare [1–{len(spare_tracks)}] | s: ").strip().lower()
        if choice == "s":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(spare_tracks):
            return spare_tracks.pop(int(choice) - 1)
        print("❗ Try again.")
