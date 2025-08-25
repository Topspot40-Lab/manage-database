# backend/services/supabase_playback.py
import logging
import subprocess
import tempfile
import os
from pathlib import Path
import asyncio
import httpx
from httpx import ReadTimeout, ConnectTimeout, RemoteProtocolError

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

logger = logging.getLogger("supabase_playback")

# ─────────────────────────────────────────────────────────────────────────────
# Robust HTTP client (shared) for audio downloads
# Timeouts & retries are env-tunable; safe defaults provided
# ─────────────────────────────────────────────────────────────────────────────
PLAYBACK_CONNECT_TIMEOUT = int(os.getenv("PLAYBACK_CONNECT_TIMEOUT", "15"))
PLAYBACK_READ_TIMEOUT    = int(os.getenv("PLAYBACK_READ_TIMEOUT", "180"))
PLAYBACK_WRITE_TIMEOUT   = int(os.getenv("PLAYBACK_WRITE_TIMEOUT", "30"))
PLAYBACK_POOL_TIMEOUT    = int(os.getenv("PLAYBACK_POOL_TIMEOUT", "180"))
PLAYBACK_MAX_RETRIES     = int(os.getenv("PLAYBACK_MAX_RETRIES", "3"))
PLAYBACK_BACKOFF_FACTOR  = float(os.getenv("PLAYBACK_BACKOFF_FACTOR", "1.8"))

_async_http = httpx.AsyncClient(
    http2=True,
    timeout=httpx.Timeout(
        connect=PLAYBACK_CONNECT_TIMEOUT,
        read=PLAYBACK_READ_TIMEOUT,
        write=PLAYBACK_WRITE_TIMEOUT,
        pool=PLAYBACK_POOL_TIMEOUT,
    ),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    headers={"Accept": "*/*", "Accept-Encoding": "gzip, deflate, br"},
)

async def _get_with_retries(url: str, *, headers: dict | None = None) -> httpx.Response:
    for attempt in range(1, PLAYBACK_MAX_RETRIES + 1):
        try:
            r = await _async_http.get(url, headers=headers)
            return r
        except (ReadTimeout, ConnectTimeout, RemoteProtocolError) as e:
            if attempt >= PLAYBACK_MAX_RETRIES:
                raise
            sleep_s = PLAYBACK_BACKOFF_FACTOR ** attempt
            logger.warning("Audio GET retry %d after %s → sleep %.1fs", attempt, e.__class__.__name__, sleep_s)
            await asyncio.sleep(sleep_s)

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

        base_args = ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error"]
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
            try:
                r = await _get_with_retries(url, headers=headers)
            except Exception as e:
                logger.error("❌ HTTP GET failed for %s/%s: %r", bucket, path, e)
                return 1

            if r.status_code != 200:
                logger.error("❌ Fetch %s/%s failed: %s %s", bucket, path, r.status_code, r.text[:200])
                return 1

            mp3_bytes = r.content
            return await asyncio.to_thread(play_mp3_bytes_sync, mp3_bytes, block=block, diagnostics=diagnostics)

    raise TypeError("play_mp3(...) expected (bytes) or (bucket, bytes|path)")
