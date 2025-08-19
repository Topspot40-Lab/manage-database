import os
from dataclasses import dataclass
from typing import List, Optional
from supabase import create_client, Client

import argparse
import time
from json import JSONDecodeError
from httpx import HTTPError


# ---- Config via env ----
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
MAKE_PUBLIC = (os.environ.get("MAKE_PUBLIC", "true").lower() == "true")
DRY_RUN = (os.environ.get("DRY_RUN", "false").lower() == "true")
CACHE_CONTROL = os.environ.get("CACHE_CONTROL", "public, max-age=31536000, immutable")

# Old (EN) buckets -> text type mapping
OLD_BUCKET_MAP = {
    "track-intro-mp3-files": "intro",
    "track-detail-mp3-files": "detail",
    "artist-mp3-files": "artist",
}

# New language buckets
NEW_BUCKETS = ["audio-en", "audio-es", "audio-ptbr"]

sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

parser = argparse.ArgumentParser(description="Migrate EN audio to language buckets")
parser.add_argument("--only", choices=["intro", "detail", "artist"], help="process only this text type")
parser.add_argument("--skip-existing", action="store_true", help="skip if destination object already exists")
parser.add_argument("--failures", default="migration_failures.txt", help="path to write failures")
args = parser.parse_args()

def object_exists(bucket: str, key: str) -> bool:
    # Split "dir/file.mp3" → parent dir and filename
    parent, _, fname = key.rpartition("/")
    try:
        # Try using 'search' if supported by your SDK
        items = sb.storage.from_(bucket).list(parent or "", {"limit": 1000, "search": fname})
    except Exception:
        # Fallback: list directory and filter
        items = sb.storage.from_(bucket).list(parent or "", {"limit": 1000})
    for it in items:
        t = _attr(it, "type", "type")
        name = _attr(it, "name", "name")
        if t != "folder" and name == fname:
            return True
    return False


@dataclass
class ObjRef:
    bucket: str
    name: str  # key inside bucket

def log(msg: str):
    print(msg, flush=True)

def _attr(obj, name: str, key: str = None):
    """Safely read attribute or dict key."""
    v = getattr(obj, name, None)
    if v is None and isinstance(obj, dict) and key:
        v = obj.get(key)
    return v
def ensure_bucket(name: str, public: bool):
    try:
        buckets = sb.storage.list_buckets()
        existing = [_attr(b, "name", "name") for b in buckets]
        if name not in existing:
            if DRY_RUN:
                log(f"DRY-RUN: would create bucket {name}")
            else:
                sb.storage.create_bucket(name)  # older SDK: no 'public' param
                log(f"✅ Created bucket: {name}")
        else:
            log(f"ℹ️ Bucket exists: {name}")
        # NOTE: We are NOT toggling public here; do it in the dashboard if needed.
        if public:
            log(f"ℹ️ To make '{name}' public, use Supabase Dashboard → Storage → {name} → Make public.")
    except Exception as e:
        raise RuntimeError(f"Bucket ensure failed for {name}: {e}")

def list_all_objects(bucket: str, prefix: str = "") -> List[ObjRef]:
    """Recursively list all files in bucket starting at prefix, with paging."""
    out: List[ObjRef] = []
    stack = [prefix.strip("/")]
    while stack:
        curr = stack.pop()
        offset = 0
        while True:
            items = sb.storage.from_(bucket).list(curr or "", {"limit": 1000, "offset": offset})
            if not items:
                break
            for it in items:
                t = _attr(it, "type", "type")         # "file" or "folder"
                name = _attr(it, "name", "name")
                if t == "folder":
                    sub = f"{curr}/{name}".strip("/")
                    stack.append(sub)
                else:
                    key = f"{curr}/{name}".strip("/")
                    out.append(ObjRef(bucket=bucket, name=key))
            if len(items) < 1000:
                break
            offset += 1000
    return out


import time
from json import JSONDecodeError
from httpx import HTTPError
MAX_RETRIES = 4

def copy_object(src: ObjRef, dst_bucket: str, dst_key: str, skip_existing: bool = False):
    # CORRECT: snake_case keys so Content-Type becomes audio/mpeg
    file_options = {
        "content_type": "audio/mpeg",
        "cache_control": "31536000",  # seconds (1 year)
    }

    # Skip if already there (for resume runs)
    if skip_existing and object_exists(dst_bucket, dst_key):
        log(f"↪️  Skip (exists) {dst_bucket}/{dst_key}")
        return

    if DRY_RUN:
        log(f"DRY-RUN: would copy {src.bucket}/{src.name} → {dst_bucket}/{dst_key}")
        return

    # 1) download
    data = sb.storage.from_(src.bucket).download(src.name)

    # 2) best-effort remove dest, so we get idempotent behavior on older SDKs
    try:
        sb.storage.from_(dst_bucket).remove([dst_key])
    except Exception:
        pass

    # 3) upload with retry/backoff (handles transient JSONDecodeError/HTTP issues)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            sb.storage.from_(dst_bucket).upload(
                dst_key,
                data,
                file_options=file_options,  # <-- use snake_case dict
            )
            log(f"📀 Copied {src.bucket}/{src.name} → {dst_bucket}/{dst_key}")
            return
        except (JSONDecodeError, HTTPError) as e:
            wait = 1.0 * attempt
            log(f"⏳ Retry {attempt}/{MAX_RETRIES} on {dst_bucket}/{dst_key} due to {type(e).__name__}: {e}. Waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            # Unknown error: bubble up so main can record failure
            raise

    log(f"❗ Gave up on {dst_bucket}/{dst_key} after {MAX_RETRIES} retries.")

def infer_dst_key(text_type: str, old_key: str) -> str:
    """
    Place old object under audio-en/{text_type}/... without duplicating the type
    if it's already present at the start of the key.
    """
    normalized = old_key.lstrip("/")
    if normalized.startswith(f"{text_type}/"):
        return normalized
    return f"{text_type}/{normalized}"

def main():
    # 1) Ensure new language buckets exist
    for b in NEW_BUCKETS:
        ensure_bucket(b, public=MAKE_PUBLIC)

    # Optional: restrict to a single text type (intro/detail/artist)
    if args.only:
        reverse = {v: k for k, v in OLD_BUCKET_MAP.items()}  # {"intro": "...", ...}
        subset = {reverse[args.only]: args.only}
    else:
        subset = OLD_BUCKET_MAP

    failures = []
    total = 0
    copied = 0

    # 2) Copy from each old EN bucket into audio-en/{type}/...
    for old_bucket, text_type in subset.items():
        log(f"\n➡️  Copying {old_bucket} → audio-en/{text_type}  (skip-existing={args.skip_existing}, dry-run={DRY_RUN})")
        log(f"🔎 Listing objects in '{old_bucket}'...")
        objs = list_all_objects(old_bucket)
        if not objs:
            log(f"  ⚠️ No objects found in {old_bucket}.")
            continue

        log(f"  Found {len(objs)} objects in {old_bucket}.")
        for idx, obj in enumerate(objs, 1):
            total += 1
            dst_key = infer_dst_key(text_type, obj.name)
            try:
                copy_object(obj, "audio-en", dst_key, skip_existing=args.skip_existing)
                copied += 1
            except Exception as e:
                log(f"❌ Failed {old_bucket}/{obj.name} → audio-en/{dst_key}: {e}")
                failures.append((old_bucket, obj.name, dst_key, str(e)))

            if idx % 100 == 0:
                log(f"  ...progress: {idx}/{len(objs)} from {old_bucket}")

    # 3) Write failures report (if any)
    if failures:
        fail_path = args.failures
        with open(fail_path, "w", encoding="utf-8") as f:
            for s_bucket, s_key, d_key, err in failures:
                f.write(f"{s_bucket},{s_key} -> audio-en/{d_key} :: {err}\n")
        log(f"\n⚠️ {len(failures)} objects failed. Details saved to {fail_path}")

    # 4) Summary + next steps
    log(f"\n✅ Migration complete. Attempted {total} objects; completed {copied - len(failures)}/{total} without fatal errors.")
    log("Next steps:")
    log("  • Point EN to 'audio-en' in your app/DB.")
    log("  • Upload ES to 'audio-es' and PT-BR to 'audio-ptbr'.")
    log("  • Verify a sampling, then remove old buckets when ready.")


if __name__ == "__main__":
    main()
