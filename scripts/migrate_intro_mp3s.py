import os
import logging
import httpx
from tqdm import tqdm

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

OLD_BUCKET = "track-intro-mp3-files"
NEW_BUCKET = "ranking-intro-mp3-files"

HEADERS = {"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("mp3_migrator")

async def migrate_file(filename: str, client: httpx.AsyncClient):
    src_url = f"{SUPABASE_URL}/storage/v1/object/{OLD_BUCKET}/{filename}"
    dest_url = f"{SUPABASE_URL}/storage/v1/object/{NEW_BUCKET}/{filename}"

    # Check if already exists in new bucket
    head_resp = await client.head(dest_url, headers=HEADERS)
    if head_resp.status_code == 200:
        logger.debug(f"🟡 Already exists, skipping: {filename}")
        return "skipped"

    # Download from old bucket
    get_resp = await client.get(src_url, headers=HEADERS)
    if get_resp.status_code != 200:
        logger.warning(f"❌ Failed to download: {filename}")
        return "failed"

    # Upload to new bucket
    put_resp = await client.put(dest_url, headers={**HEADERS, "Content-Type": "audio/mpeg"}, content=get_resp.content)
    if put_resp.status_code in (200, 201):
        logger.info(f"✅ Copied: {filename}")
        return "copied"
    else:
        logger.error(f"❌ Upload failed for {filename} → {put_resp.text}")
        return "failed"

async def run():
    import asyncio

    # 🔍 Get file list
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/{OLD_BUCKET}"
    async with httpx.AsyncClient() as client:
        list_resp = await client.get(list_url, headers=HEADERS)
        if list_resp.status_code != 200:
            logger.error("❌ Failed to list files.")
            return

        files = [f["name"] for f in list_resp.json() if f["name"].endswith(".mp3")]
        logger.info(f"📦 Found {len(files)} MP3 files to migrate...\n")

        results = await asyncio.gather(*(migrate_file(f, client) for f in tqdm(files)))

        # Summary
        copied = results.count("copied")
        skipped = results.count("skipped")
        failed = results.count("failed")
        logger.info(f"\n✅ Done. Copied: {copied}, Skipped: {skipped}, Failed: {failed}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
