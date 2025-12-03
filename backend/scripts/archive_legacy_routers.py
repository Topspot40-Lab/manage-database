from __future__ import annotations
import shutil
from pathlib import Path

LEGACY_ROUTERS = [
    "supabase_loader_legacy.py",
    "supabase_loader_old.py",
    "collections_generate_old.py",
    "metadata_seed.py",
    "tts_artist.py",            # loads but contains 0 routes
    "tts_collection_intro.py",  # loads but contains 0 routes
    "tts_detail.py",            # loads but contains 0 routes
    "tts_intro.py",             # loads but contains 0 routes
]

def main():
    base = Path(__file__).resolve().parents[1] / "routers"
    archive = base / "_archive"

    # Create archive directory if needed
    archive.mkdir(exist_ok=True)

    moved = []
    skipped = []

    for filename in LEGACY_ROUTERS:
        source = base / filename
        if source.exists():
            target = archive / filename
            shutil.move(str(source), str(target))
            moved.append(filename)
        else:
            skipped.append(filename)

    print("\n🐴 Mr. Ed — Legacy Router Archiver\n")
    print("📁 Archive directory:", archive)
    print("\n📦 Moved files:")
    for f in moved:
        print("  -", f)

    print("\n⏭ Skipped (not found):")
    for f in skipped:
        print("  -", f)

    print("\n✨ Done! Legacy routers archived safely.\n")


if __name__ == "__main__":
    main()
