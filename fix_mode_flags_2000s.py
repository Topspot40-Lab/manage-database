import json
from pathlib import Path
from enum import Enum
import shutil

# 🎯 ModeFlag as string-based Enum (safe for JSON string values)
class ModeFlag(str, Enum):
    SOLO = "SOLO"
    DUET = "DUET"
    FEATURED = "FEATURED"
    GROUP = "GROUP"
    UNKNOWN = "UNKNOWN"

def fix_mode_flag(track: dict) -> None:
    raw = track.get("mode_flag")

    if isinstance(raw, int):
        int_to_enum = {
            0: ModeFlag.SOLO,
            1: ModeFlag.FEATURED,
            2: ModeFlag.DUET,
            3: ModeFlag.GROUP,
            99: ModeFlag.UNKNOWN
        }
        new_val = int_to_enum.get(raw, ModeFlag.UNKNOWN).value
        if raw != new_val:
            print(f"🔁 mode_flag: {raw} → {new_val}")
        track["mode_flag"] = new_val

    elif isinstance(raw, str):
        try:
            normalized = raw.strip().upper()
            new_val = ModeFlag[normalized].value
            if raw != new_val:
                print(f"🔁 mode_flag: {raw} → {new_val}")
            track["mode_flag"] = new_val
        except KeyError:
            print(f"⚠️ Unknown mode_flag: {raw}, defaulting to UNKNOWN")
            track["mode_flag"] = ModeFlag.UNKNOWN.value

# 🧼 Fix a single file
def fix_file(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    modified = False
    for track in data.get("track_tables", {}).get("track", []):
        before = track.get("mode_flag")
        fix_mode_flag(track)
        after = track.get("mode_flag")
        if before != after:
            modified = True

    if modified:
        # 🔒 Backup original file
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)

        # 📝 Save updated file
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"✅ Fixed and backed up: {path.name} → {backup_path.name}")
    else:
        print(f"⏭️ No changes needed: {path.name}")

# 🚀 Main program
def main():
    target_dir = Path("data/json_files/genredecade/2000s")

    if not target_dir.exists():
        print(f"❌ Directory not found: {target_dir}")
        return

    print(f"📂 Scanning directory: {target_dir}")
    for file in target_dir.glob("*.json"):
        fix_file(file)

if __name__ == "__main__":
    main()
