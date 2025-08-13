import re
import sys
import argparse
from pathlib import Path
import requests

ROOT_DEFAULT = Path(__file__).resolve().parents[1]  # repo root if placed in tools/
GLOBS = ["**/*.md", "**/*.html", "**/*.py", "**/*.js", "**/*.ts", "**/*.json"]
HTTP_RE = re.compile(r'http://[^\s)"\'<>]+', re.IGNORECASE)

SKIP_PREFIXES = (
    "http://localhost",
    "http://127.0.0.1",
)
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}

session = requests.Session()
session.headers["User-Agent"] = "TopSpot-HTTP-Upgrader/1.0"

def https_ok(url: str, timeout=6) -> bool:
    """Check if https version of url is reachable. HEAD first, fallback to GET on 405."""
    https_url = "https://" + url[len("http://"):]
    try:
        r = session.head(https_url, allow_redirects=True, timeout=timeout)
        if r.status_code == 405:  # Method Not Allowed
            r = session.get(https_url, allow_redirects=True, timeout=timeout, stream=True)
            r.close()
        return r.status_code < 400
    except Exception:
        return False

def should_skip_path(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)

def process_file(p: Path, dry_run: bool = True) -> int:
    text = p.read_text(encoding="utf-8", errors="ignore")
    changes = 0

    def repl(m):
        nonlocal changes
        url = m.group(0)
        if url.startswith(SKIP_PREFIXES):
            return url
        if https_ok(url):
            changes += 1
            return "https://" + url[len("http://"):]
        return url

    new = HTTP_RE.sub(repl, text)
    if changes and not dry_run:
        p.write_text(new, encoding="utf-8")
    return changes

def main():
    ap = argparse.ArgumentParser(description="Upgrade http:// links to https:// where safe.")
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT, help="Repository root")
    ap.add_argument("--apply", action="store_true", help="Apply changes (otherwise dry-run)")
    args = ap.parse_args()

    total_changed = 0
    for g in GLOBS:
        for p in args.root.glob(g):
            if not p.is_file():
                continue
            if should_skip_path(p):
                continue
            total_changed += process_file(p, dry_run=not args.apply)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"{mode}: upgraded {total_changed} link(s).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
