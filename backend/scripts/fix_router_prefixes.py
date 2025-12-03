# backend/scripts/fix_router_prefixes.py
"""
🐴 Mr. Ed — Router Prefix Normalizer (Auto Mode)

This script:
 - Reads your official prefix map
 - Scans all routers under backend/routers/
 - Detects incorrect APIRouter(prefix="...")
 - Automatically rewrites them with the correct prefix
 - Creates .bak backups of changed files
 - Prints a clean before/after report
"""

from __future__ import annotations

import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ROUTER_DIR = ROOT / "backend" / "routers"

# ---------------------------------------------------------
# 🟨 OFFICIAL PREFIX MAP (Gary-approved)
# ---------------------------------------------------------
PREFIX_MAP = {
    "JSON & Files": "/json",
    "Supabase": "/supabase",
    "Supabase: Decade/Genre": "/supabase/decade-genre",
    "Supabase: Collections": "/supabase/collections",
    "Playback": "/playback",
    "Narration": "/narration",
    "Generators": "/generate",
    "Locales": "/locales",
    "Upsert/Import": "/import",
    "Meta": "/meta",
    "Spotify Auth": "/spotify",
    "Catalog": "/catalog",
}

# ---------------------------------------------------------
# Helper: Extract APIRouter(...) line
# ---------------------------------------------------------
ROUTER_RE = re.compile(
    r"router\s*=\s*APIRouter\s*\(\s*(.*?)\s*\)",
    flags=re.DOTALL
)

PREFIX_KV_RE = re.compile(
    r'prefix\s*=\s*[\'"]([^\'"]*)[\'"]'
)

TAGS_RE = re.compile(
    r'tags\s*=\s*\[([^\]]*)\]'
)


def extract_tag(text: str) -> str | None:
    """Extract the first tag=... list inside APIRouter."""
    m = TAGS_RE.search(text)
    if not m:
        return None

    raw = m.group(1)
    tag_match = re.search(r"[\"']([^\"']+)[\"']", raw)
    return tag_match.group(1).strip() if tag_match else None


def extract_prefix(text: str) -> str | None:
    m = PREFIX_KV_RE.search(text)
    return m.group(1) if m else None


def replace_prefix_block(block: str, new_prefix: str) -> str:
    """Rewrite prefix='...' inside APIRouter(...) block."""
    if "prefix=" not in block:
        # Insert prefix argument
        if block.strip().endswith(","):
            return block.replace("(", f"(prefix=\"{new_prefix}\", ", 1)
        else:
            return block.replace("(", f"(prefix=\"{new_prefix}\", ", 1)

    # Replace existing prefix
    return PREFIX_KV_RE.sub(f'prefix="{new_prefix}"', block)


def process_router_file(path: Path):
    text = path.read_text(encoding="utf-8")

    # Extract router config
    m = ROUTER_RE.search(text)
    if not m:
        return None  # Not a router file

    block = m.group(1)

    tag = extract_tag(block)
    prefix = extract_prefix(block)

    if not tag:
        return None  # No tag → skip modification

    if tag not in PREFIX_MAP:
        return None  # Tag not in approved list → skip

    expected = PREFIX_MAP[tag]

    if prefix == expected:
        return None  # Already correct

    # Fix the prefix
    new_block = replace_prefix_block(block, expected)
    new_text = text.replace(block, new_block)

    # Backup
    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_path.write_text(text, encoding="utf-8")

    # Write new
    path.write_text(new_text, encoding="utf-8")

    return {
        "file": path.name,
        "old": prefix,
        "new": expected,
    }


def run():
    print("\n🐴 Mr. Ed — Router Prefix Normalizer (AUTO MODE)\n")

    results = []

    for py in ROUTER_DIR.glob("*.py"):
        res = process_router_file(py)
        if res:
            results.append(res)

    if not results:
        print("✨ No fixes needed. Everything is already clean!")
        return

    print(f"{'File':30} {'Old Prefix':20} {'→'} {'New Prefix'}")
    print("-" * 75)
    for r in results:
        print(f"{r['file']:30} {str(r['old']):20} → {r['new']}")

    print("\n🏁 Done! Backup files (*.bak) created.\n")


if __name__ == "__main__":
    run()

