# backend/services/supabase_playback.py
from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger("supabase_playback")

# ─────────────────────────────────────────────
# GLOBAL PLAYBACK STATE (critical)
# ─────────────────────────────────────────────

# The currently-running ffplay process
_current_proc: Optional[subprocess.Popen] = None

# Prevent multiple simultaneous audio plays
_play_lock = asyncio.Lock()


def _kill_existing_proc():
    """
    Kill any running ffplay process.
    Called before starting new audio OR on stop/skip.
    """
    global _current_proc

    proc = _current_proc
    if proc is None:
        return

    try:
        if proc.poll() is None:
            logger.debug("🛑 Killing previous ffplay instance...")
            try:
                proc.terminate()
            except Exception:
                pass

            try:
                proc.kill()
            except Exception:
                pass
    except Exception as e:
        logger.warning("⚠️ Error killing ffplay: %s", e)
    finally:
        _current_proc = None


# ─────────────────────────────────────────────
# HIGH-LEVEL PUBLIC API
# ─────────────────────────────────────────────

async def play_mp3(
    mp3_bytes: bytes,
    *,
    block: bool = True,
    diagnostics: bool = False
) -> int:
    """
    The ONLY playback entry point used by safe_play().
    - Enforces exclusive playback (no overlap)
    - Kills previous track immediately
    - Plays new track
    - Respects stop/skip logic via cancellation
    - Works on Windows and macOS/Linux
    """
    global _current_proc

    # One-at-a-time playback
    async with _play_lock:

        # Kill any leftover audio
        _kill_existing_proc()

        # Write temp file
        try:
            tmpdir = tempfile.TemporaryDirectory()
            mp3_path = Path(tmpdir.name) / "clip.mp3"
            mp3_path.write_bytes(mp3_bytes)
        except Exception as e:
            logger.error("❌ Could not write temp MP3: %s", e)
            return 1

        # ffplay command
        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-hide_banner",
            "-loglevel",
            "error" if not diagnostics else "info",
            str(mp3_path),
        ]

        logger.debug("▶️ ffplay starting…")

        try:
            _current_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            logger.error("❌ ffplay not found. Install FFmpeg.")
            return 127
        except Exception as e:
            logger.error("❌ Failed to start ffplay: %s", e)
            return 1

        # Non-blocking mode
        if not block:
            logger.debug("▶️ Non-blocking ffplay pid=%s", _current_proc.pid)
            return 0

        # Blocking mode
        try:
            rc = await asyncio.to_thread(_current_proc.wait)
            logger.debug("🎧 ffplay finished rc=%s", rc)
            return rc

        except asyncio.CancelledError:
            logger.info("🛑 Playback cancelled; killing ffplay")
            _kill_existing_proc()
            raise

        except Exception as e:
            logger.error("⚠️ ffplay wait error: %s", e)
            _kill_existing_proc()
            return 1

        finally:
            # cleanup
            _current_proc = None
            try:
                tmpdir.cleanup()
            except Exception:
                pass


# ─────────────────────────────────────────────
# EXTERNAL STOP HOOK
# Called by: playback_control.stop() + skip_event
# ─────────────────────────────────────────────
def stop_audio():
    """
    Immediately kill any running audio.
    Frontend calls /playback/stop → backend sets flags → this kills ffplay.
    """
    _kill_existing_proc()
    logger.info("🛑 stop_audio(): any running ffplay was terminated")
