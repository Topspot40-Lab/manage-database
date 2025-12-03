# backend/scripts/scan_router_registry.py
"""
Scan all routers and print a detailed registry report:
 - filename
 - router prefix
 - router-level tags
 - number of routes
 - whether included in main.py
 - detects duplicate prefixes
 - ASCII + color output
"""

import ast
import os
import re
from pathlib import Path

# ─────────────────────────────────────────────
# Terminal Colors
# ─────────────────────────────────────────────
class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    END = "\033[0m"
    BOLD = "\033[1m"


ROOT = Path(__file__).resolve().parents[1]
ROUTERS_DIR = ROOT / "routers"
MAIN_FILE = ROOT / "main.py"


# ─────────────────────────────────────────────
# Extract include_router entries from main.py
# ─────────────────────────────────────────────
def extract_main_includes():
    text = MAIN_FILE.read_text(encoding="utf-8")
    includes = re.findall(r"include_router\(([^)]+)\)", text)
    return text, includes



# ─────────────────────────────────────────────
# Parse a router file and extract metadata
# ─────────────────────────────────────────────
def parse_router(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"⚠️  Could not decode {path.name} using UTF-8.")
        return None

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    router_prefix = None
    router_tags = None
    route_count = 0

    for node in ast.walk(tree):
        # Look for: router = APIRouter(prefix="...", tags=[...])
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") == "APIRouter":
                for kw in node.value.keywords:
                    if kw.arg == "prefix":
                        router_prefix = ast.literal_eval(kw.value)
                    if kw.arg == "tags":
                        try:
                            router_tags = ast.literal_eval(kw.value)
                        except Exception:
                            router_tags = None

        # Count @router.get/post/…
        if isinstance(node, ast.Call) and hasattr(node.func, "attr"):
            if node.func.attr in ("get", "post", "put", "delete"):
                if hasattr(node.func.value, "id") and node.func.value.id == "router":
                    route_count += 1

    return {
        "path": path,
        "file": path.name,
        "prefix": router_prefix or "",
        "tags": router_tags or [],
        "route_count": route_count,
        "text": text,
    }


# ─────────────────────────────────────────────
# Main Scan Function
# ─────────────────────────────────────────────
def scan():
    print(C.BOLD + C.CYAN + "\n🐴 Mr. Ed — Router Registry Scan\n" + C.END)

    main_text, includes = extract_main_includes()

    routers = []
    for py in sorted(ROUTERS_DIR.glob("*.py")):
        info = parse_router(py)
        if info:
            routers.append(info)

    # Detect duplicate prefixes
    prefix_map = {}
    for r in routers:
        prefix_map.setdefault(r["prefix"], []).append(r["file"])

    # Pretty print header
    print(C.BOLD + f"{'Router File':30} {'Prefix':20} {'Tag':28} {'Routes':8} {'Included?':10} {'Duplicates?'}" + C.END)
    print("-" * 120)

    for r in routers:
        file = r["file"]
        prefix = r["prefix"]
        tag = ", ".join(r["tags"]) if r["tags"] else "—"
        count = r["route_count"]

        included = file.replace(".py", "") in main_text
        included_color = C.GREEN + "YES" + C.END if included else C.RED + "NO" + C.END

        dup = len(prefix_map[prefix]) > 1
        dup_color = (C.RED + "YES" + C.END) if dup else "NO"

        # Highlight problematic lines
        prefix_color = C.YELLOW + prefix + C.END if dup else prefix

        print(f"{file:30} {prefix_color:20} {tag:28} {str(count):8} {included_color:10} {dup_color}")

    # Duplicate prefix summary
    print("\n" + C.BOLD + "📌 Duplicate Prefix Analysis:" + C.END)
    for prefix, files in prefix_map.items():
        if len(files) > 1:
            print(C.RED + f"  ⚠ Prefix {prefix!r} used by: {files}" + C.END)

    print("\n" + C.GREEN + "Scan complete!" + C.END)


if __name__ == "__main__":
    scan()
