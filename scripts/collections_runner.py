#!/usr/bin/env python
import os, sys, json, pathlib, requests

API = os.getenv("TOPSPOT_API", "http://127.0.0.1:8000")
OUT_DIR = pathlib.Path("out")
OUT_DIR.mkdir(exist_ok=True)

def list_collections(kind="SPECIALTY", q=None, limit=200):
    params = {"type": kind, "limit": limit}
    if q:
        params["q"] = q
    r = requests.get(f"{API}/collections-read", params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["items"]

def pick(items):
    print("\nCollections:")
    for i, c in enumerate(items, 1):
        name = c.get("name")
        slug = c.get("slug")
        intro = c.get("intro") or ""
        print(f"{i:2d}. {name}  [{slug}]")
        if intro:
            print(f"    – {intro[:120]}{'…' if len(intro) > 120 else ''}")
    while True:
        sel = input("\nPick a number (or 'q' to quit): ").strip().lower()
        if sel in ("q", "quit", "exit"):
            sys.exit(0)
        if sel.isdigit() and 1 <= int(sel) <= len(items):
            return items[int(sel) - 1]
        print("Invalid choice. Try again.")

def generate(slug, as_file=False, include_spotify=True, include_artwork=True):
    params = {
        "as_file": as_file,
        "include_spotify": str(include_spotify).lower(),
        "include_artwork": str(include_artwork).lower(),
    }
    r = requests.get(f"{API}/collections/{slug}/generate-json", params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def maybe_save(payload, slug):
    out_path = OUT_DIR / f"{slug}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nSaved JSON → {out_path}")
    return out_path

def maybe_import(payload, dry_run=False, strict=True, replace=False):
    # augment payload with control flags if your server reads them; if not, ignore.
    payload = dict(payload)  # shallow copy
    payload["dry_run"] = dry_run
    payload["strict"] = strict
    payload["replace"] = replace

    r = requests.post(f"{API}/collections/import-json", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def main():
    print(f"TopSpot API: {API}")
    q = None
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        print(f"Filter: {q}")

    # 1) list + pick
    items = list_collections(kind="SPECIALTY", q=q)
    if not items:
        print("No collections found with that filter.")
        sys.exit(1)
    chosen = pick(items)
    slug, name = chosen["slug"], chosen["name"]
    print(f"\nSelected: {name}  [{slug}]")

    # 2) generate JSON
    payload = generate(slug, as_file=False, include_spotify=True, include_artwork=True)
    print(f"Generated {len(payload.get('tracks', []))} tracks for '{name}'")

    # 3) save to file
    out_path = maybe_save(payload, slug)

    # 4) optional import
    do_import = input("Import into DB now? [y/N]: ").strip().lower() == "y"
    if do_import:
        strict = input("Strict (fail if unresolved)? [Y/n]: ").strip().lower() not in ("n", "no")
        dry_run = input("Dry run (no writes)? [y/N]: ").strip().lower() == "y"
        replace = input("Replace mode (delete ranks not in this payload)? [y/N]: ").strip().lower() == "y"
        result = maybe_import(payload, dry_run=dry_run, strict=strict, replace=replace)
        print("\nImport result:")
        print(json.dumps(result, indent=2))
    else:
        print("\nSkipped import. You can POST the saved file later:")
        print(f"  curl -X POST {API}/collections/import-json \\")
        print(f"       -H 'Content-Type: application/json' \\")
        print(f"       --data-binary '@{out_path}'")

if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print("HTTP error:", e.response.text)
        sys.exit(1)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)
