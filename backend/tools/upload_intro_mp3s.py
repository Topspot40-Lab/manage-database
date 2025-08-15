# backend/tools/upload_intro_mp3s.py
from __future__ import annotations
import argparse, os
from pathlib import Path
import logging
from supabase import create_client
from dotenv import load_dotenv
from storage3.utils import StorageException

load_dotenv()

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SERVICE_KEY   = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

log = logging.getLogger("upload_intro_mp3s")

def get_client():
    if not SUPABASE_URL or not SERVICE_KEY:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in env/.env")
    return create_client(SUPABASE_URL, SERVICE_KEY)

def main():
    p = argparse.ArgumentParser(description="Upload local intro MP3s to Supabase (overwrite by default).")
    p.add_argument("--bucket", default="track-intro-mp3-files", help="Supabase bucket name")
    p.add_argument("--local-dir", type=Path, default=Path("data/mp3_files/track_intro_mp3_files"))
    p.add_argument("--prefix", default="", help="Path prefix in bucket (e.g. 'intros/' or 'v2/')")
    p.add_argument("--no-overwrite", action="store_true", help="Fail if exists instead of overwrite")
    p.add_argument("--cache", default="3600", help="cache-control seconds")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = p.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))
    supabase = get_client()
    storage = supabase.storage.from_(args.bucket)

    if not args.local_dir.exists():
        raise SystemExit(f"Local dir not found: {args.local_dir}")

    files = sorted(p for p in args.local_dir.glob("*.mp3") if p.is_file())
    if not files:
        log.info("No MP3s found in %s", args.local_dir)
        return

    prefix = args.prefix.strip().strip("/")
    uploaded = created = replaced = skipped = 0

    for local_path in files:
        rel_name = local_path.name
        remote_path = f"{prefix}/{rel_name}" if prefix else rel_name

        log.info("%s %s -> %s/%s",
                 "(dry-run) would upload" if args.dry_run else "uploading",
                 local_path, args.bucket, remote_path)

        if args.dry_run:
            continue

        with open(local_path, "rb") as f:
            if args.no_overwrite:
                try:
                    storage.upload(
                        path=remote_path,
                        file=f,
                        file_options={
                            # hyphenated keys match the API headers
                            "upsert": "false",
                            "content-type": "audio/mpeg",
                            "cache-control": str(args.cache),
                        },
                    )
                    created += 1
                except StorageException as e:
                    if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                        log.warning("exists, skipping: %s", remote_path)
                        skipped += 1
                    else:
                        raise
            else:
                # 1) try upsert in one shot
                try:
                    storage.upload(
                        path=remote_path,
                        file=f,
                        file_options={
                            "upsert": "true",                # ask server to overwrite
                            "content-type": "audio/mpeg",
                            "cache-control": str(args.cache),
                        },
                    )
                    # if it existed, this effectively replaced; if not, it created
                    replaced += 1
                except StorageException as e:
                    # 2) some client versions still return Duplicate; force replace
                    if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                        log.info("Duplicate reported; deleting then re-uploading: %s", remote_path)
                        storage.remove([remote_path])
                        f.seek(0)
                        storage.upload(
                            path=remote_path,
                            file=f,
                            file_options={
                                "upsert": "false",
                                "content-type": "audio/mpeg",
                                "cache-control": str(args.cache),
                            },
                        )
                        replaced += 1
                    else:
                        raise

        uploaded += 1

    log.info(
        "Done. %d file(s) processed. (%d replaced, %d created, %d skipped)",
        uploaded, replaced, created, skipped
    )

if __name__ == "__main__":
    main()
