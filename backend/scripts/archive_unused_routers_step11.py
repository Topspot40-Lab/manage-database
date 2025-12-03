#!/usr/bin/env python3
"""
Mr. Ed — Step 11
Safely archive unused or broken router modules detected in Step 10.
"""

import shutil
from pathlib import Path

ROOT = Path("backend/routers")
ARCHIVE = ROOT / "_archive"

# These were confirmed UNUSED by Step 10
TO_ARCHIVE = [
    "supabase_loader_legacy.py",
    "tts_shared.py",
]

def main():
    print("\n🐴 Mr. Ed — Step 11: Router Archiver\n")

    ARCHIVE.mkdir(exist_ok=True)

    moved = []
    skipped = []

    for filename in TO_ARCHIVE:
        src = ROOT / filename
        dst = ARCHIVE / filename

        if src.exists():
            print(f"📦 Archiving {filename} → _archive/")
            shutil.move(str(src), str(dst))
            moved.append(filename)
        else:
            print(f"⚠ Skipped (not found): {filename}")
            skipped.append(filename)

    print("\n──────── SUMMARY ────────")
    print(f"Moved: {len(moved)} file(s)")
    for f in moved:
        print(f"   ✔ {f}")

    if skipped:
        print(f"\nSkipped (missing): {len(skipped)}")
        for f in skipped:
            print(f"   ⚠ {f}")

    print("\n🏁 Step 11 complete — unused routers safely archived.\n")

if __name__ == "__main__":
    main()
