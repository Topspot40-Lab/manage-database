# backend/services/supabase_playback.py

import logging

import subprocess
import tempfile
import os
from pathlib import Path

logger = logging.getLogger("supabase_playback")

def play_mp3(mp3_bytes: bytes, *, block: bool = True, diagnostics: bool = False) -> int:
    """
    Save bytes to a temp .mp3 (Windows-safe) and play with ffplay.
    Returns ffplay returncode (0 on success). Raises no exception.
    """
    # 1) Write to a closed temp file (delete=False so Windows doesn't lock it)
    tmp = tempfile.NamedTemporaryFile(prefix="ts_", suffix=".mp3", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(mp3_bytes)
        tmp.flush()
        tmp.close()  # very important on Windows

        # 2) Build the command (no shell, each arg separate)
        #    Start with more verbose logging while diagnosing
        base_args = ["ffplay", "-nodisp", "-autoexit"]
        if diagnostics:
            # Show errors (remove -loglevel quiet), add -hide_banner to reduce noise
            base_args += ["-hide_banner", "-loglevel", "error"]
        else:
            base_args += ["-hide_banner", "-loglevel", "error"]

        cmd = base_args + [str(tmp_path)]

        logger.info(f"▶ ffplay starting: {cmd!r}")
        try:
            if block:
                proc = subprocess.run(
                    cmd,
                    check=False,            # we’ll inspect returncode and log
                    capture_output=True     # capture stderr/stdout for error logs
                )
                if proc.returncode != 0:
                    # Surface helpful diagnostics
                    if proc.stderr:
                        logger.error(f"ffplay stderr: {proc.stderr.decode(errors='ignore')}")
                    if proc.stdout:
                        logger.debug(f"ffplay stdout: {proc.stdout.decode(errors='ignore')}")
                    logger.error(f"❌ ffplay failed with returncode={proc.returncode}")
                else:
                    logger.info("✅ ffplay completed")
                return proc.returncode
            else:
                # Non-blocking variant (rarely needed for your TTS flow)
                subprocess.Popen(cmd)
                return 0
        except FileNotFoundError:
            logger.error("❌ ffplay not found in PATH. Install FFmpeg and ensure ffplay is available.")
            return 127
        except Exception as e:
            logger.exception(f"❌ Unexpected error launching ffplay: {e}")
            return 1
    finally:
        # 3) Clean up the temp file
        try:
            os.remove(tmp_path)
        except Exception as e:
            logger.warning(f"⚠️ Could not remove temp file {tmp_path}: {e}")
