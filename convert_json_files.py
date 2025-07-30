import json
from pathlib import Path
from datetime import datetime, UTC


def convert_old_to_new_json(input_path: Path, output_path: Path):
    with open(input_path, "r", encoding="utf-8") as f:
        old = json.load(f)

    language = old.get("language", "english")
    category = old.get("category")
    genre = old.get("genre")
    generated_at = old.get("generated_at", datetime.now(UTC).isoformat())

    core = old.get("core_tables", {})
    track_tables = old.get("track_tables", {})
    ranking_tables = old.get("ranking_tables", {})

    new = {
        "language": language,
        "category": category,
        "genre": genre,
        "generated_at": generated_at,
        "genre_table": core.get("genre", []),
        "decade": core.get("decade", []),
        "artist": core.get("artist", []),
        "track": track_tables.get("track", []),
        "tracklist": track_tables.get("tracklist", []),
        "track_ranking": [],
        "artist_table": []
    }

    for entry in ranking_tables.get("track_ranking", []):
        new_entry = entry.copy()
        if "ranking_date" in new_entry:
            new_entry["created_at"] = new_entry.pop("ranking_date")
        new["track_ranking"].append(new_entry)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2)

    print(f"✅ Converted: {input_path.name}")
    print(f"   ├── Tracks:   {len(new['track'])}")
    print(f"   ├── Artists:  {len(new['artist'])}")
    print(f"   └── Rankings: {len(new['track_ranking'])}\n")

def batch_convert(input_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_files = list(input_dir.glob("*.json"))

    if not json_files:
        print(f"⚠️ No JSON files found in: {input_dir}")
        return

    print(f"🚀 Converting {len(json_files)} files from {input_dir} to {output_dir}...\n")

    for file in json_files:
        output_file = output_dir / file.name

        if output_file.exists():
            print(f"⏩ Skipping (already exists): {file.name}\n")
            continue

        try:
            convert_old_to_new_json(file, output_file)
        except Exception as e:
            print(f"❌ Failed to convert {file.name}: {e}\n")

if __name__ == "__main__":
    input_folder = Path("data/json_files/genredecade/2000s")

    output_folder = Path("data/json_files/converted")

    batch_convert(input_folder, output_folder)
