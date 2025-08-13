# backend/services/supabase_playback.py
import logging
import subprocess
import tempfile
import os
from pathlib import Path
import asyncio
import httpx

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

logger = logging.getLogger("supabase_playback")


# ------------------------------
# Low-level: sync player (bytes)
# ------------------------------
def play_mp3_bytes_sync(mp3_bytes: bytes, *, block: bool = True, diagnostics: bool = False) -> int:
    """
    Save bytes to a temp .mp3 (Windows-safe) and play with ffplay.
    Returns ffplay returncode (0 on success). Never raises.
    """
    tmp = tempfile.NamedTemporaryFile(prefix="ts_", suffix=".mp3", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(mp3_bytes)
        tmp.flush()
        tmp.close()  # important on Windows

        # Build command (no shell; args as list)
        base_args = ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error"]
        if diagnostics:
            # You can tweak loglevel here if you want more noise while debugging
            pass

        cmd = base_args + [str(tmp_path)]
        logger.debug("▶ ffplay starting")

        if block:
            proc = subprocess.run(cmd, check=False, capture_output=True)
            if proc.returncode != 0:
                if proc.stderr:
                    logger.error("ffplay stderr: %s", proc.stderr.decode(errors="ignore"))
                if proc.stdout:
                    logger.debug("ffplay stdout: %s", proc.stdout.decode(errors="ignore"))
                logger.error("❌ ffplay failed with returncode=%s", proc.returncode)
            else:
                logger.debug("✅ ffplay completed")
            return proc.returncode
        else:
            subprocess.Popen(cmd)
            return 0

    except FileNotFoundError:
        logger.error("❌ ffplay not found in PATH. Install FFmpeg and ensure ffplay is available.")
        return 127
    except Exception as e:
        logger.exception("❌ Unexpected error launching ffplay: %s", e)
        return 1
    finally:
        try:
            os.remove(tmp_path)
        except Exception as e:
            logger.warning("⚠️ Could not remove temp file %s: %s", tmp_path, e)


# ---------------------------------------------------
# High-level: async wrapper (backward-compatible API)
# ---------------------------------------------------
async def play_mp3(*args, block: bool = True, diagnostics: bool = False) -> int:
    """
    Backward-compatible async wrapper.

    Accepts either:
      1) play_mp3(mp3_bytes)
      2) play_mp3(bucket: str, path_or_bytes: str|bytes)

    Returns ffplay return code (0 on success).
    """
    # New form: bytes only
    if len(args) == 1:
        mp3_bytes = args[0]
        if not isinstance(mp3_bytes, (bytes, bytearray)):
            raise TypeError("play_mp3(bytes) expected bytes")
        return await asyncio.to_thread(play_mp3_bytes_sync, mp3_bytes, block=block, diagnostics=diagnostics)

    # Old forms: (bucket, bytes) or (bucket, path)
    if len(args) == 2:
        bucket, second = args

        # (bucket, bytes) — already fetched elsewhere
        if isinstance(second, (bytes, bytearray)):
            return await asyncio.to_thread(play_mp3_bytes_sync, second, block=block, diagnostics=diagnostics)

        # (bucket, path) — fetch from Supabase Storage, then play
        if isinstance(bucket, str) and isinstance(second, str):
            path = second
            url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
            headers = {"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url, headers=headers)
                if r.status_code != 200:
                    logger.error("Failed to fetch %s/%s: %s %s", bucket, path, r.status_code, r.text[:200])
                    return 1
                mp3_bytes = r.content
            return await asyncio.to_thread(play_mp3_bytes_sync, mp3_bytes, block=block, diagnostics=diagnostics)

    raise TypeError("play_mp3(...) expected (bytes) or (bucket, bytes|path)")
