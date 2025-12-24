# backend/services/playback_helpers.py
from __future__ import annotations

import asyncio
import logging
import httpx
import os
import inspect
from typing import Literal, Optional

from backend.config import BUCKETS, AUDIO_PREFIXES, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.supabase_playback import play_mp3

# 🔑 Single source of truth for playback state
from backend.state.playback_state import (
    status,
    update_phase,
)

from backend.services.spotify.playback import play_spotify_track, stop_spotify_playback
from backend.services.play_policy import compute_play_seconds, sleep_with_skip
from backend.state.skip import skip_event

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Playback User-Control Helpers
# ─────────────────────────────────────────────

async def _respect_user_controls() -> None:
    """Pause / stop cooperative checkpoint."""
    while status.is_paused:
        await asyncio.sleep(0.25)

    if status.stopped:
        logger.info("🛑 Playback stopped by user.")
        raise asyncio.CancelledError("Playback stopped")


def _update_state_for_play(kind: str, bucket: str, key: str) -> None:
    """Mark which audio asset is currently playing."""
    update_phase(
        kind.lower(),
        is_playing=True,
        is_paused=False,
        stopped=False,
        context={
            "bucket": bucket,
            "key": key,
        },
    )


# ─────────────────────────────────────────────
# Speech + Language Helpers
# ─────────────────────────────────────────────

Lang = Literal["en", "es", "pt-BR"]
Kind = Literal["intro", "detail", "artist", "collections_intro"]

_LANG_MAP: dict[str, str] = {
    "en": "en",
    "es": "es",
    "ptbr": "pt-BR",
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "pt": "pt-BR",
}

def canon_lang(code: str | None) -> str:
    c = (code or "en").strip().lower()
    return _LANG_MAP.get(c, "en")


# ─────────────────────────────────────────────
# Tunables & Gain
# ─────────────────────────────────────────────

_SUPA_FETCH_TIMEOUT = float(os.getenv("SUPA_MP3_TIMEOUT", "60"))
_SUPA_FETCH_RETRIES = int(os.getenv("SUPA_MP3_RETRIES", "3"))
_SUPA_BACKOFF = float(os.getenv("SUPA_MP3_BACKOFF", "1.8"))

try:
    from backend.config import INTRO_GAIN_DB, DETAIL_GAIN_DB, ARTIST_GAIN_DB
except Exception:
    INTRO_GAIN_DB = float(os.getenv("INTRO_GAIN_DB", "-4.0"))
    DETAIL_GAIN_DB = float(os.getenv("DETAIL_GAIN_DB", "0.0"))
    ARTIST_GAIN_DB = float(os.getenv("ARTIST_GAIN_DB", "0.0"))

_play_lock = asyncio.Lock()


# ─────────────────────────────────────────────
# Bucket / Key Builders
# ─────────────────────────────────────────────

def bucket_for(language: str, kind: Kind) -> str:
    lang = canon_lang(language)
    lang_map = BUCKETS.get(lang, BUCKETS["en"])

    if kind in lang_map:
        return lang_map[kind]

    if kind == "collections_intro":
        return lang_map.get("intro")

    return lang_map.get("intro")


def key_for(kind: Kind, filename: str | None) -> Optional[str]:
    if not filename:
        return None

    prefix = AUDIO_PREFIXES.get(kind)
    if prefix is None and kind == "collections_intro":
        prefix = "collections-intro"

    if prefix is None:
        return None

    return f"{prefix}/{filename}"


def build_intro_filename(decade: str, genre: str, rank: int) -> str:
    return f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02d}.mp3"


def build_collection_intro_filename(slug: str, rank: int) -> str:
    return f"{normalize_for_filename(slug)}_{rank:02d}.mp3"


def build_detail_filename(spotify_track_id: str | None) -> Optional[str]:
    return f"{spotify_track_id}.mp3" if spotify_track_id else None


def build_artist_filename(spotify_artist_id: str | None) -> Optional[str]:
    return f"{spotify_artist_id}.mp3" if spotify_artist_id else None


# ─────────────────────────────────────────────
# Gain Mapping
# ─────────────────────────────────────────────

def _gain_for_kind(kind_label: str) -> float:
    k = (kind_label or "").strip().lower()
    if k in ("intro", "collections_intro"):
        return INTRO_GAIN_DB
    if k == "detail":
        return DETAIL_GAIN_DB
    if k == "artist":
        return ARTIST_GAIN_DB
    return 0.0


# ─────────────────────────────────────────────
# MP3 Playback (Local ffplay)
# ─────────────────────────────────────────────

def _looks_like_mp3(b: bytes) -> bool:
    return b.startswith(b"ID3") or (
        len(b) > 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0
    )


async def _play_bytes_with_gain(b: bytes, gain_db: float) -> int:
    """Play MP3 bytes using ffplay with a simple volume filter."""
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
            logger.warning("ffplay volume-filter failed: %s", e)
            return 1


# ─────────────────────────────────────────────
# safe_play — robust MP3 playback from Supabase
# ─────────────────────────────────────────────

async def safe_play(kind: str, bucket: str, key: str) -> bool:
    if not (bucket and key):
        logger.warning("🚫 %s MP3 not attempted (empty bucket/key)", kind)
        return False

    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{key}"
    headers = {"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}

    # HEAD probe
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            head = await client.head(url, headers=headers)
        if head.status_code != 200:
            logger.warning(
                "❌ %s MP3 missing: %s/%s (status=%s)",
                kind, bucket, key, head.status_code
            )
            return False
    except Exception:
        pass

    gain_db = _gain_for_kind(kind)
    last_err = None

    async with _play_lock:
        for attempt in range(1, _SUPA_FETCH_RETRIES + 1):
            try:
                await _respect_user_controls()
                _update_state_for_play(kind, bucket, key)

                async with httpx.AsyncClient(timeout=_SUPA_FETCH_TIMEOUT) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    b = await resp.aread()

                if len(b) < 1024 or not _looks_like_mp3(b):
                    raise RuntimeError("Bad MP3 download")

                await _respect_user_controls()

                if abs(gain_db) > 0.05:
                    rc = await _play_bytes_with_gain(b, gain_db)
                else:
                    res = play_mp3(b, block=True, diagnostics=False)
                    rc = await res if inspect.iscoroutine(res) else res

                if rc == 0:
                    return False  # finished normally

                last_err = f"ffplay rc={rc}"

            except asyncio.CancelledError:
                logger.info("🛑 %s playback cancelled by user", kind)
                return False
            except Exception as e:
                last_err = e
                logger.warning(
                    "⚠️ %s exception attempt %d/%d: %s",
                    kind, attempt, _SUPA_FETCH_RETRIES, e
                )

            if attempt < _SUPA_FETCH_RETRIES:
                await asyncio.sleep(_SUPA_BACKOFF ** attempt)

    logger.error(
        "❌ %s MP3 gave up after %d attempts: %s/%s :: %s",
        kind, _SUPA_FETCH_RETRIES, bucket, key, last_err
    )
    return False


# ─────────────────────────────────────────────
# 🎵 Spotify Track Playback
# ─────────────────────────────────────────────

async def play_track_with_skip(
    track,
    *,
    lang: str,
    mode: str,
    rank: int,
    track_name: str,
    artist_name: str,
) -> bool:
    spotify_id = getattr(track, "spotify_track_id", None)
    if not spotify_id:
        logger.warning("🚫 No spotify_track_id for %s — skipping.", track_name)
        return False

    try:
        await stop_spotify_playback(fade_out_seconds=0.8)
    except Exception:
        pass

    update_phase(
        "track",
        is_playing=True,
        language=lang,
        mode=mode,
        context={
            "spotify_track_id": spotify_id,
            "rank": rank,
            "track_name": track_name,
            "artist_name": artist_name,
        },
    )

    await _respect_user_controls()

    logger.info("🎵 Playing Spotify track: %s — rank %s", track_name, rank)
    if not play_spotify_track(spotify_id):
        logger.warning("❌ Spotify refused playback.")
        return False

    play_secs = compute_play_seconds(track)
    skipped = await sleep_with_skip(skip_event, play_secs)

    try:
        await stop_spotify_playback(fade_out_seconds=1.0)
    except Exception:
        pass

    return skipped
