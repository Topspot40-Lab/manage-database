#!/usr/bin/env python3
"""
Mr. Ed — Tag Quote Cleaner (Advanced Version)

Fixes tags like:
    ["'Meta'"] → ["Meta"]
    ['Meta'] → ["Meta"]
    ["Meta"] → ["Meta"]
    ['"Meta"'] → ["Meta"]
"""

import re
from pathlib import Path

BASE = Path("backend/routers")

# Match variations like:
# tags=["'Meta'", "'Playback'"]
# tags=['Meta', 'Something']
TAG_PATTERN = re.compile(
    r"tags=\s*\[\s*([^\]]*?)\s*\]"
)

def clean_tag_value(tag: str) -> str:
    tag = tag.strip()

    # remove leading/trailing commas
    tag = tag.strip(",")

    # remove ALL surrounding quotes (single or double)
    # "'Meta'" → Meta
    while (tag.startswith(("'", '"')) and tag.endswith(("'", '"'))):
        tag = tag[1:-1].strip()

    return tag

def process_file(path: Path):
    original = path.read_text(encoding="utf-8")

    def repl(match):
        inside = match.group(1)

        # Split on commas at top level
        raw_tags = [t.strip() for t in inside.split(",") if t.strip()]

        cleaned_tags = [f'"{clean_tag_value(t)}"' for t in raw_tags]

        return f"tags=[{', '.join(cleaned_tags)}]"

    updated = TAG_PATTERN.sub(repl, original)

    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main():
    print("\n🐴 Mr. Ed — Tag Quote Cleaner (Advanced)\n")

    changed = 0
    for file in BASE.glob("*.py"):
        if file.name.startswith("_"):
            continue
        if process_file(file):
            print(f"✅ Cleaned: {file.name}")
            changed += 1

    print(f"\n🏁 Done! {changed} files updated.\n")


if __name__ == "__main__":
    main()
