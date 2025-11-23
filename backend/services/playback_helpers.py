# backend/services/playback_helpers.py
from __future__ import annotations

from typing import Literal, Optional
import logging
import asyncio
import httpx
import os
import time
import inspect

from backend.config import BUCKETS, AUDIO_PREFIXES, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.supabase_playback import play_mp3

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Playback control integration
# ─────────────────────────────────────────────
from backend.routers.playback_control import _flags  # global playback state


async def _respect_user_controls() -> None:
    """Pause or stop check (cooperative)."""
    while getattr(_flags, "is_paused", False):
        await asyncio.sleep(0.25)
    if getattr(_flags, "stopped", False):
        logger.info("🛑 Playback stopped by user.")
        raise asyncio.CancelledError("Playback stopped")


def _update_flags_for_play(kind: str, bucket: str, key: str) -> None:
    """Helper to mark which MP3 is currently playing."""
    try:
        _flags.is_playing = True
        _flags.is_paused = False
        _flags.stopped = False
        phase = kind.lower()
        _flags.context = {
            "phase": phase,
            "bucket": bucket,
            "key": key,
        }
    except Exception:
        logger.debug("⚠️ Failed to update playback flags for %s", kind)


# 🔁 Canonical language codes (pt-BR)
Lang = Literal["en", "es", "pt-BR"]

# ➕ include collections_intro as a 4th kind (plural to match narration_bundle + config)
Kind = Literal["intro", "detail", "artist", "collections_intro"]

_LANG_MAP: dict[str, str] = {
    "en": "en",
    "es": "es",
    "ptbr": "pt-BR",
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "pt": "pt-BR",
}

# Tunables (env overrides)
_SUPA_FETCH_TIMEOUT = float(os.getenv("SUPA_MP3_TIMEOUT", "60"))
_SUPA_FETCH_RETRIES = int(os.getenv("SUPA_MP3_RETRIES", "3"))
_SUPA_BACKOFF = float(os.getenv("SUPA_MP3_BACKOFF", "1.8"))

# 🔊 Per-kind gain (dB). Prefer config, else fall back to env with sane defaults
try:
    from backend.config import INTRO_GAIN_DB, DETAIL_GAIN_DB, ARTIST_GAIN_DB  # type: ignore
except Exception:
    INTRO_GAIN_DB = float(os.getenv("INTRO_GAIN_DB", "-4.0"))
    DETAIL_GAIN_DB = float(os.getenv("DETAIL_GAIN_DB", "0.0"))
    ARTIST_GAIN_DB = float(os.getenv("ARTIST_GAIN_DB", "0.0"))

_play_lock = asyncio.Lock()


def _looks_like_mp3(b: bytes) -> bool:
    return b.startswith(b"ID3") or (len(b) > 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0)


def canon_lang(code: str | None) -> str:
    c = (code or "en").strip().lower()
    return _LANG_MAP.get(c, "en")


def bucket_for(language: str, kind: Kind) -> str:
    """
    Return the Supabase bucket name for a given language/kind.
    Falls back to the 'intro' bucket if 'collections_intro' is not explicitly configured.
    """
    lang = canon_lang(language)
    lang_map = BUCKETS.get(lang, BUCKETS["en"])

    if kind in lang_map:
        return lang_map[kind]

    # graceful fallback for new kind without config change
    if kind == "collections_intro":
        return lang_map.get("intro")

    # final fallback (shouldn't really happen)
    return lang_map.get("intro")


def key_for(kind: Kind, filename: str | None) -> Optional[str]:
    """
    Build the storage key (folder + filename) for a given kind.
    If AUDIO_PREFIXES lacks 'collections_intro', default to 'collections-intro'.
    """
    if not filename:
        return None

    prefix = AUDIO_PREFIXES.get(kind)

    if prefix is None and kind == "collections_intro":
        prefix = "collections-intro"

    if prefix is None:
        return None

    return f"{prefix}/{filename}"


def build_intro_filename(decade: str, genre: str, rank: int) -> str:
    """
    Decade/Genre intro filename, zero-padded 2 digits.
    e.g., '1980s_pop_01.mp3'
    """
    return f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02d}.mp3"


def build_collection_intro_filename(slug: str, rank: int) -> str:
    """
    Collection intro filename, two-digit padding (will naturally grow to 100, 101…).
    e.g., slug='power-ballads' -> 'power-ballads_01.mp3'
    """
    return f"{normalize_for_filename(slug)}_{rank:02d}.mp3"


def build_detail_filename(spotify_track_id: str | None) -> Optional[str]:
    return f"{spotify_track_id}.mp3" if spotify_track_id else None


def build_artist_filename(spotify_artist_id: str | None) -> Optional[str]:
    return f"{spotify_artist_id}.mp3" if spotify_artist_id else None


def _gain_for_kind(kind_label: str) -> float:
    """
    Map kind label to gain. Treat 'collections_intro' the same as 'intro'.
    """
    k = (kind_label or "").strip().lower()
    if k in ("intro", "collections_intro"):
        return INTRO_GAIN_DB
    if k == "detail":
        return DETAIL_GAIN_DB
    if k == "artist":
        return ARTIST_GAIN_DB

    # tolerate Title-case callers
    if kind_label in ("Intro", "CollectionsIntro"):
        return INTRO_GAIN_DB
    if kind_label == "Detail":
        return DETAIL_GAIN_DB
    if kind_label == "Artist":
        return ARTIST_GAIN_DB

    return 0.0


async def _play_bytes_with_gain(b: bytes, gain_db: float) -> int:
    """
    Play MP3 bytes using ffplay with a simple volume filter, blocking until done.
    Returns ffplay's exit code (0 on success).
    """
    import tempfile
    import subprocess
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "clip.mp3"
        src.write_bytes(b)
        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-hide_banner",
            "-loglevel",
            "error",
            "-af",
            f"volume={gain_db}dB",
            str(src),
        ]
        try:
            return subprocess.call(cmd)
        except Exception as e:
            logger.warning("ffplay with volume filter failed: %s", e)
            return 1


async def safe_play(kind: str, bucket: str, key: str) -> bool:
    """
    Robust MP3 playback from Supabase with HEAD probe, GET retries, and
    sequential playback (locked). Returns True on success.

    kind: "Intro" | "Detail" | "Artist" | "CollectionsIntro"
    """
    if not (bucket and key):
        logger.warning("🚫 %s MP3 not attempted (empty bucket/key)", kind)
        return False

    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{key}"
    headers = {"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}

    # Quick existence probe (non-fatal if it fails)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            head = await client.head(url, headers=headers)
        if head.status_code != 200:
            logger.warning(
                "❌ %s MP3 missing: %s/%s (status=%s)",
                kind,
                bucket,
                key,
                head.status_code,
            )
            return False
    except Exception as e:
        logger.debug(
            "HEAD failed for %s %s/%s: %s (will try GET)",
            kind,
            bucket,
            key,
            e,
        )

    last_err: object | None = None
    gain_db = _gain_for_kind(kind)

    async with _play_lock:
        for attempt in range(1, _SUPA_FETCH_RETRIES + 1):
            try:
                # Respect pause/stop between retries
                await _respect_user_controls()

                _update_flags_for_play(kind, bucket, key)
                t0 = time.perf_counter()

                async with httpx.AsyncClient(timeout=_SUPA_FETCH_TIMEOUT) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    b = await resp.aread()

                size = len(b or b"")
                if size < 1024:
                    raise RuntimeError(f"Downloaded size too small: {size} bytes")
                if not _looks_like_mp3(b):
                    raise RuntimeError("Not an MP3 (bad header)")

                # Respect pause/stop before playing
                await _respect_user_controls()

                # Apply gain if configured; else fast path
                if abs(gain_db) > 0.05:
                    rc = await _play_bytes_with_gain(b, gain_db)
                else:
                    res = play_mp3(b, block=True, diagnostics=False)
                    rc = await res if inspect.iscoroutine(res) else res

                dt = time.perf_counter() - t0
                if rc == 0:
                    logger.debug(
                        "✅ %s MP3 played in %.2fs (%s/%s) [bytes=%d, rc=%d]",
                        kind,
                        dt,
                        bucket,
                        key,
                        size,
                        rc,
                    )
                    return True

                last_err = f"ffplay rc={rc}"
                logger.warning(
                    "⚠️ %s play failed (attempt %d/%d) rc=%s %s/%s",
                    kind,
                    attempt,
                    _SUPA_FETCH_RETRIES,
                    rc,
                    bucket,
                    key,
                )

            except asyncio.CancelledError:
                logger.info("🛑 %s playback cancelled by user", kind)
                return False
            except Exception as e:
                last_err = e
                logger.warning(
                    "⚠️ %s MP3 exception (attempt %d/%d) %s/%s: %s",
                    kind,
                    attempt,
                    _SUPA_FETCH_RETRIES,
                    bucket,
                    key,
                    e,
                )

            if attempt < _SUPA_FETCH_RETRIES:
                await asyncio.sleep(_SUPA_BACKOFF ** attempt)

    logger.error(
        "❌ %s MP3 gave up after %d attempts: %s/%s :: %s",
        kind,
        _SUPA_FETCH_RETRIES,
        bucket,
        key,
        last_err,
    )
    return False
