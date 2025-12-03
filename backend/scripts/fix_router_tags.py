# backend/scripts/fix_router_tags.py
"""
Mr. Ed's Router Tag Fixer 🐴✨

Automatically scans all routers, identifies APIRouter definitions,
and rewrites the tags so they match the canonical list in main.py.

Creates .bak backups before modifying each file.

Run with:
    python backend/scripts/fix_router_tags.py
"""

import re
import sys
from pathlib import Path

# ─────────────────────────────────────────────
# CANONICAL TAG MAP (authoritative truth)
# ─────────────────────────────────────────────
TAG_MAP = {
    "spotify_auth": "Spotify Auth",
    "playback_control": "Playback",
    "decade_genre_player": "Supabase: Decade/Genre",
    "supabase_loader": "Supabase",
    "supabase_summary": "Supabase",
    "collections_player": "Supabase: Collections",
    "collections_read": "Supabase: Collections",
    "collections_generate": "Supabase: Collections",
    "collections": "Supabase: Collections",
    "tts_regenerator": "Narration",
    "tts_intro": "Narration",
    "tts_detail": "Narration",
    "tts_artist": "Narration",
    "narration": "Narration",
    "play_json_track_by_rank": "Playback",
    "generate_json": "JSON & Files",
    "validate_json": "JSON & Files",
    "insert_json": "JSON & Files",
    "router_saved_files": "JSON & Files",
    "upsert_json": "Upsert/Import",
    "track_detail_locales": "Locales",
    "artist_locales": "Locales",
    "intros_locales": "Locales",
    "generate_poprock": "Generators",
    "generate_folk_acoustic": "Generators",
    "enrich_tv_themes": "Generators",
    "expand_tv_themes": "Generators",
    "catalog": "Catalog",
    "ads_scripts": "Meta",
    "meta_logging": "Meta",
}

# ─────────────────────────────────────────────
# Regex pattern to locate APIRouter definitions
# ─────────────────────────────────────────────
ROUTER_PATTERN = re.compile(
    r"router\s*=\s*APIRouter\((.*?)\)",
    re.DOTALL
)

TAG_PATTERN = re.compile(
    r"tags\s*=\s*\[(.*?)\]"
)


def fix_router_file(file_path: Path):
    module_name = file_path.stem
    correct_tag = TAG_MAP.get(module_name)

    if not correct_tag:
        return None  # No automatic rule for this router

    original = file_path.read_text(encoding="utf-8")
    modified = original

    matches = ROUTER_PATTERN.finditer(original)
    changed = False

    for m in matches:
        full_router = m.group(0)

        # If router lacks tags OR tags mismatch → rewrite
        if "tags=" not in full_router or correct_tag not in full_router:
            new_router = re.sub(
                TAG_PATTERN,
                f'tags=["{correct_tag}"]',
                full_router
            )

            # If no tags existed, add them
            if full_router == new_router:
                # Insert tags argument before anything else
                new_router = full_router.replace(
                    "APIRouter(",
                    f'APIRouter(tags=["{correct_tag}"], '
                )

            modified = modified.replace(full_router, new_router)
            changed = True

    if changed:
        # Backup
        file_path.with_suffix(file_path.suffix + ".bak").write_text(
            original, encoding="utf-8"
        )
        # Write new file
        file_path.write_text(modified, encoding="utf-8")
        return correct_tag

    return None


def main():
    routers_dir = Path("backend/routers")
    if not routers_dir.exists():
        print("❌ backend/routers not found.")
        sys.exit(1)

    print("\n🐴 Mr. Ed is fixing your router tags...\n")

    changes = []
    for file in routers_dir.glob("*.py"):
        result = fix_router_file(file)
        if result:
            changes.append((file.name, result))

    if not changes:
        print("✨ No changes needed — everything is already perfect!")
    else:
        print("✅ Updated router tags:")
        for filename, tag in changes:
            print(f"  • {filename:35} → {tag}")

    print("\n🏁 Done. Backup files (*.bak) created where changes occurred.\n")


if __name__ == "__main__":
    main()
