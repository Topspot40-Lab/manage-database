import os, ssl, time, argparse
from typing import List
import httpx
from supabase import create_client, Client

URL = os.environ["SUPABASE_URL"].strip()
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
sb: Client = create_client(URL, KEY)

RETRYABLE = (httpx.ReadError, httpx.HTTPError, ssl.SSLError, ConnectionError, TimeoutError)

def _attr(o, name, key=None):
    v = getattr(o, name, None)
    if v is None and isinstance(o, dict) and key: v = o.get(key)
    return v

def get_mimetype(bucket: str, key: str) -> str:
    """Read mimetype from storage.objects.metadata for this object."""
    # The Python client exposes Postgrest via `sb._postgrest`
    res = sb._postgrest.from_("storage.objects") \
        .select("metadata") \
        .eq("bucket_id", bucket) \
        .eq("name", key) \
        .limit(1) \
        .execute()
    rows = res.data or []
    if not rows: return ""
    md = rows[0].get("metadata") or {}
    return (md.get("mimetype") or "").strip()

def list_bad(bucket: str, prefix: str) -> List[str]:
    """Find mp3s under prefix whose stored mimetype != audio/mpeg."""
    bad = []
    stack = [prefix.strip("/")]
    while stack:
        curr = stack.pop()
        offset = 0
        while True:
            items = sb.storage.from_(bucket).list(curr or "", {"limit": 1000, "offset": offset})
            if not items: break
            for it in items:
                t = _attr(it, "type", "type")
                name = _attr(it, "name", "name")
                md = _attr(it, "metadata", "metadata") or {}
                if t == "folder":
                    stack.append(f"{curr}/{name}".strip("/"))
                else:
                    key = f"{curr}/{name}".strip("/")
                    if key.endswith(".mp3") and (md.get("mimetype") != "audio/mpeg"):
                        bad.append(key)
            if len(items) < 1000: break
            offset += 1000
    return bad

def download_with_retry(bucket: str, key: str, retries=5, base_delay=1.0):
    last = None
    for i in range(1, retries+1):
        try:
            return sb.storage.from_(bucket).download(key)
        except RETRYABLE as e:
            last = e
            d = base_delay * i
            print(f"⏳ download retry {i}/{retries} for {bucket}/{key}: {e} (sleep {d:.1f}s)")
            time.sleep(d)
    raise last

def upload_set_mime(bucket: str, key: str, data: bytes, style: str):
    """Upload with a given option style ('snake' or 'camel') and set metadata.mimetype."""
    try:
        sb.storage.from_(bucket).remove([key])  # best-effort
    except Exception:
        pass
    if style == "snake":
        opts = {"content_type": "audio/mpeg", "cache_control": "31536000", "metadata": {"mimetype": "audio/mpeg"}}
    else:
        opts = {"contentType": "audio/mpeg", "cacheControl": "31536000", "metadata": {"mimetype": "audio/mpeg"}}
    sb.storage.from_(bucket).upload(key, data, file_options=opts)

def repair_one(bucket: str, key: str, retries=5, base_delay=1.0):
    """Try snake_case upload, verify; if still wrong, try camelCase; verify again."""
    data = download_with_retry(bucket, key, retries=retries, base_delay=base_delay)

    # Attempt 1: snake_case options
    for attempt in range(1, retries+1):
        try:
            upload_set_mime(bucket, key, data, style="snake")
            break
        except RETRYABLE as e:
            d = base_delay * attempt
            print(f"⏳ upload(snake) retry {attempt}/{retries} for {bucket}/{key}: {e} (sleep {d:.1f}s)")
            time.sleep(d)
    # Verify
    mt = get_mimetype(bucket, key)
    if mt == "audio/mpeg":
        return True

    # Attempt 2: camelCase options
    for attempt in range(1, retries+1):
        try:
            upload_set_mime(bucket, key, data, style="camel")
            break
        except RETRYABLE as e:
            d = base_delay * attempt
            print(f"⏳ upload(camel) retry {attempt}/{retries} for {bucket}/{key}: {e} (sleep {d:.1f}s)")
            time.sleep(d)

    # Verify again
    mt = get_mimetype(bucket, key)
    return (mt == "audio/mpeg")

def repair_prefix(bucket: str, prefix: str, retries=5, base_delay=1.0, failures_path="mime_repair_failures.txt"):
    todo = list_bad(bucket, prefix)
    print(f"[{bucket}/{prefix}] to fix: {len(todo)}")
    if not todo: return
    failed = 0
    for i, key in enumerate(todo, 1):
        ok = False
        try:
            ok = repair_one(bucket, key, retries=retries, base_delay=base_delay)
        except Exception as e:
            print(f"❌ {bucket}/{key} unexpected error: {e}")
        if ok:
            print(f"✅ fixed {bucket}/{key}")
        else:
            print(f"❗ still wrong {bucket}/{key}")
            with open(failures_path, "a", encoding="utf-8") as f:
                f.write(f"{bucket},{key}\n")
            failed += 1
        if i % 100 == 0:
            print(f"[{prefix}] progress {i}/{len(todo)} (failures so far: {failed})")
    if failed:
        print(f"⚠️ {failed} files still not showing audio/mpeg. See {failures_path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="audio-en")
    ap.add_argument("--prefix", action="extend", nargs="+", default=["artist","detail","intro"])
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--base-delay", type=float, default=1.0)
    ap.add_argument("--failures", default="mime_repair_failures.txt")
    args = ap.parse_args()

    for p in args.prefix:
        repair_prefix(args.bucket, p, retries=args.retries, base_delay=args.base_delay, failures_path=args.failures)
    print("done")
