# backend/tools/migrate_audio_buckets.py
"""
Migrate old EN audio buckets into new language buckets.

- Old buckets:
    track-intro-mp3-files  -> text type "intro"
    track-detail-mp3-files -> "detail"
    artist-mp3-files       -> "artist"

- New EN bucket layout:
    audio-en/<type>/...    (e.g., audio-en/intro/1950s_country_01.mp3)
"""

import os
import argparse
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Set

from supabase import create_client, Client
from json import JSONDecodeError
from httpx import HTTPError

# ─────────────────────────────────────────────────────────────────────────────
# Config via env
# ─────────────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
MAKE_PUBLIC = (os.environ.get("MAKE_PUBLIC", "true").lower() == "true")
DRY_RUN = (os.environ.get("DRY_RUN", "false").lower() == "true")

# Old (EN) buckets -> text type mapping
OLD_BUCKET_MAP = {
    "track-intro-mp3-files": "intro",
    "track-detail-mp3-files": "detail",
    "artist-mp3-files": "artist",
}

# New language buckets
NEW_BUCKETS = ["audio-en", "audio-es", "audio-ptbr"]

# Upload options (snake_case for current SDKs)
FILE_OPTIONS = {
    "content_type": "audio/mpeg",
    "cache_control": "31536000",  # seconds (1 year)
}

MAX_RETRIES = 4

sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(msg, flush=True)

def _attr(obj, name: str, key: Optional[str] = None):
    """Safely read attribute or dict key."""
    v = getattr(obj, name, None)
    if v is None and isinstance(obj, dict) and key:
        v = obj.get(key)
    return v

@dataclass
class ObjRef:
    bucket: str
    name: str  # key inside bucket

def ensure_bucket(name: str, public: bool) -> None:
    try:
        buckets = sb.storage.list_buckets()
        existing = [_attr(b, "name", "name") for b in buckets]
        if name not in existing:
            if DRY_RUN:
                log(f"DRY-RUN: would create bucket {name}")
            else:
                sb.storage.create_bucket(name)  # older SDK may ignore 'public'
                log(f"✅ Created bucket: {name}")
        else:
            log(f"ℹ️ Bucket exists: {name}")
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

def list_all_keys(bucket: str, prefix: str = "") -> Set[str]:
    """Return a set of keys under a prefix for fast existence checks."""
    return {obj.name for obj in list_all_objects(bucket, prefix)}

def infer_dst_key(text_type: str, old_key: str) -> str:
    """
    Place old object under audio-en/{text_type}/... without duplicating the type
    if it's already present at the start of the key.
    """
    normalized = old_key.lstrip("/")
    if normalized.startswith(f"{text_type}/"):
        return normalized
    return f"{text_type}/{normalized}"

def copy_object(src: ObjRef, dst_bucket: str, dst_key: str) -> None:
    if DRY_RUN:
        log(f"DRY-RUN: would copy {src.bucket}/{src.name} → {dst_bucket}/{dst_key}")
        return

    # 1) download
    data = sb.storage.from_(src.bucket).download(src.name)

    # 2) best-effort remove dest to be idempotent on older SDKs
    try:
        sb.storage.from_(dst_bucket).remove([dst_key])
    except Exception:
        pass

    # 3) upload with retry/backoff
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            sb.storage.from_(dst_bucket).upload(dst_key, data, file_options=FILE_OPTIONS)
            log(f"📀 Copied {src.bucket}/{src.name} → {dst_bucket}/{dst_key}")
            return
        except (JSONDecodeError, HTTPError) as e:
            wait = float(attempt)  # 1s, 2s, 3s, ...
            log(f"⏳ Retry {attempt}/{MAX_RETRIES} on {dst_bucket}/{dst_key} due to {type(e).__name__}: {e}. Waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            raise
    log(f"❗ Gave up on {dst_bucket}/{dst_key} after {MAX_RETRIES} retries.")

def count_intro_files() -> None:
    src = len(list_all_objects("track-intro-mp3-files"))
    dst = len(list_all_objects("audio-en", "intro/"))
    log(f"Source intro files: {src}")
    log(f"Dest   intro files: {dst}")
    if dst < src:
        log(f"⚠️ {src - dst} intro file(s) still missing from audio-en/intro/")

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Migrate EN audio to language buckets")
parser.add_argument("--only", choices=["intro", "detail", "artist"], help="process only this text type")
parser.add_argument("--skip-existing", action="store_true", help="skip if destination object already exists")
parser.add_argument("--failures", default="migration_failures.txt", help="path to write failures")
parser.add_argument("--retry-failures", action="store_true", help="retry items listed in --failures file and exit")
parser.add_argument("--verify-only", action="store_true", help="print source/dest counts (intro) and exit")
args = parser.parse_args()

def main() -> None:
    # 0) just verify counts and exit
    if args.verify_only:
        count_intro_files()
        return

    # 1) Ensure new language buckets exist
    for b in NEW_BUCKETS:
        ensure_bucket(b, public=MAKE_PUBLIC)

    # 2) Retry a previous failures file and exit
    if args.retry_failures:
        fail_path = args.failures
        if not os.path.exists(fail_path):
            log(f"no failures file at {fail_path}")
            return
        with open(fail_path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        for ln in lines:
            # format: old_bucket,old_key -> audio-en/dst_key :: error
            left, _, rest = ln.partition("->")
            src_bucket, _, src_key = left.strip().partition(",")
            dst_full = rest.split("::", 1)[0].strip()         # " audio-en/<dst_key>"
            dst_key = dst_full.split("/", 1)[1] if "/" in dst_full else dst_full
            try:
                copy_object(ObjRef(src_bucket.strip(), src_key.strip()), "audio-en", dst_key.strip())
            except Exception as e:
                log(f"❌ still failing: {src_bucket}/{src_key} -> audio-en/{dst_key}: {e}")
        return

    # Optional: restrict to a single text type (intro/detail/artist)
    if args.only:
        reverse = {v: k for k, v in OLD_BUCKET_MAP.items()}  # {"intro": "...", ...}
        subset = {reverse[args.only]: args.only}
    else:
        subset = OLD_BUCKET_MAP

    # 3) Pre-index existing dest keys (only if skipping existing)
    existing_by_type: Dict[str, Set[str]] = {}
    if args.skip_existing:
        log("🔎 Pre-indexing destination keys for skip-existing...")
        for ttype in set(subset.values()):
            prefix = f"{ttype}/"
            existing_by_type[ttype] = list_all_keys("audio-en", prefix)
            log(f"  • {ttype}: {len(existing_by_type[ttype])} existing keys under audio-en/{prefix}")

    failures = []
    total = 0
    copied = 0

    # 4) Copy from each old EN bucket into audio-en/{type}/...
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

            if args.skip_existing and dst_key in existing_by_type.get(text_type, set()):
                log(f"↪️  Skip (exists) audio-en/{dst_key}")
                continue

            try:
                copy_object(obj, "audio-en", dst_key)
                copied += 1
            except Exception as e:
                log(f"❌ Failed {old_bucket}/{obj.name} → audio-en/{dst_key}: {e}")
                failures.append((old_bucket, obj.name, dst_key, str(e)))

            if idx % 100 == 0:
                log(f"  ...progress: {idx}/{len(objs)} from {old_bucket}")

    # 5) Write failures report (if any)
    if failures:
        fail_path = args.failures
        with open(fail_path, "w", encoding="utf-8") as f:
            for s_bucket, s_key, d_key, err in failures:
                f.write(f"{s_bucket},{s_key} -> audio-en/{d_key} :: {err}\n")
        log(f"\n⚠️ {len(failures)} objects failed. Details saved to {fail_path}")

    # 6) Summary + next steps
    log(f"\n✅ Migration complete. Attempted {total} objects; completed {copied - len(failures)}/{total} without fatal errors.")
    count_intro_files()
    log("Next steps:")
    log("  • Point EN to 'audio-en' in your app/DB.")
    log("  • Upload ES to 'audio-es' and PT-BR to 'audio-ptbr'.")
    log("  • Verify a sampling, then remove old buckets when ready.")

if __name__ == "__main__":
    main()
