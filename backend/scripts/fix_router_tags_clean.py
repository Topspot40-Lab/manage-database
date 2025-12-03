# backend/scripts/fix_router_tags_clean.py
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "routers"

# Canonical tag mapping
TAG_MAP = {
    "meta": "Meta",
    "catalog": "Catalog",
    "locales": "Locales",
    "supabase: collections": "Supabase: Collections",
    "supabase: decade/genre": "Supabase: Decade/Genre",
    "supabase": "Supabase",
    "generators": "Generators",
    "json & files": "JSON & Files",
    "playback": "Playback",
    "narration": "Narration",
    "tts": "TTS",
    "tts - track intros & details": "TTS",
}

# Tags we should delete entirely
BAD_TAGS = {
    "Collections (Generate JSON)",
    "metadata",
}

def canonicalize(tag: str) -> str:
    key = tag.strip().lower()
    return TAG_MAP.get(key, tag)

def fix_tags_in_file(path: Path):
    text = path.read_text(encoding="utf-8")
    original = text

    # Match tags=[ ... ]
    pattern = r"tags\s*=\s*\[([^\]]*)\]"

    def repl(match):
        content = match.group(1)
        tags = [t.strip().strip("'\"") for t in content.split(",") if t.strip()]

        cleaned = []
        for t in tags:
            if t in BAD_TAGS:
                continue
            cleaned.append(canonicalize(t))

        # remove duplicates while preserving order
        cleaned_unique = list(dict.fromkeys(cleaned))

        return f"tags={[repr(t) for t in cleaned_unique]}"

    new_text = re.sub(pattern, repl, text)

    if new_text != original:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def run():
    print("\n🐴 Mr. Ed — Tag Normalizer Running\n")
    changed = 0

    for file in ROOT.glob("*.py"):
        if file.name.startswith("_"):
            continue

        if fix_tags_in_file(file):
            print(f"✅ Cleaned tags in {file.name}")
            changed += 1

    print("\n🏁 Done! Files updated:" if changed else "\n✨ Everything already clean!")
    print(f"Total files changed: {changed}\n")


if __name__ == "__main__":
    run()
