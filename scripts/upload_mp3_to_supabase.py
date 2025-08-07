# backend/tools/upload_mp3_files.py (or wherever this lives)

from pathlib import Path
import mimetypes
import os
from dotenv import load_dotenv
from backend.services.supabase_client import supabase  # ✅ Use shared client!

# 📥 Load .env just in case (optional here, already loaded in supabase_client)
load_dotenv()

# 🔄 Map local subfolders to Supabase bucket names
BUCKET_MAP = {
    "track_intro_mp3_files": "track-intro-mp3-files",
    "track_detail_mp3_files": "track-detail-mp3-files",
    "artist_mp3_files": "artist-mp3-files",
}

MP3_ROOT = Path(__file__).resolve().parent.parent / "data" / "mp3_files"

def upload_mp3_files():
    print(f"🔐 Using Supabase URL: {os.getenv('SUPABASE_URL')}")

    for folder, bucket in BUCKET_MAP.items():
        local_folder = MP3_ROOT / folder
        if not local_folder.exists():
            print(f"⚠️ Folder not found: {local_folder}")
            continue

        for file_path in local_folder.glob("*.mp3"):
            supabase_path = file_path.name
            content_type, _ = mimetypes.guess_type(file_path)

            try:
                with open(file_path, "rb") as f:
                    supabase.storage.from_(bucket).upload(
                        path=supabase_path,
                        file=f,
                        file_options={"content-type": content_type or "audio/mpeg"},
                    )
                print(f"✅ Uploaded: {bucket}/{supabase_path}")
            except Exception as e:
                print(f"❌ Failed: {bucket}/{supabase_path} — {e}")

if __name__ == "__main__":
    upload_mp3_files()
