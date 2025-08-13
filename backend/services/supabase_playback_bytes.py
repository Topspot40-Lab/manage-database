import subprocess
import tempfile
import os
from pathlib import Path
import logging

logger = logging.getLogger("supabase_playback")

def play_mp3_bytes_sync(mp3_bytes: bytes, *, block: bool = True, diagnostics: bool = False) -> int:
    tmp = tempfile.NamedTemporaryFile(prefix="ts_", suffix=".mp3", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(mp3_bytes)
        tmp.flush()
        tmp.close()

        base_args = ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "error"]
        cmd = base_args + [str(tmp_path)]
        logger.info("▶ ffplay starting")

        if block:
            proc = subprocess.run(cmd, check=False, capture_output=True)
            if proc.returncode != 0:
                if proc.stderr:
                    logger.error("ffplay stderr: %s", proc.stderr.decode(errors="ignore"))
                if proc.stdout:
                    logger.debug("ffplay stdout: %s", proc.stdout.decode(errors="ignore"))
                logger.error("❌ ffplay failed with returncode=%s", proc.returncode)
            else:
                logger.info("✅ ffplay completed")
            return proc.returncode
        else:
            subprocess.Popen(cmd)
            return 0
    except FileNotFoundError:
        logger.error("❌ ffplay not found in PATH.")
        return 127
    except Exception as e:
        logger.exception("❌ Unexpected error launching ffplay: %s", e)
        return 1
    finally:
        try:
            os.remove(tmp_path)
        except Exception as e:
            logger.warning("⚠️ Could not remove temp file %s: %s", tmp_path, e)
