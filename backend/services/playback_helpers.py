# backend/services/playback_helpers.py
from typing import Literal, Optional
import logging, asyncio, httpx, os, time
import inspect
from backend.config import BUCKETS, AUDIO_PREFIXES, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.services.supabase_playback import play_mp3

logger = logging.getLogger(__name__)

Lang  = Literal["en", "es", "ptbr"]
Kind  = Literal["intro", "detail", "artist"]

_LANG_MAP = {"en": "en", "es": "es", "ptbr": "pt-BR"}

# Tunables (env overrides)
_SUPA_FETCH_TIMEOUT = float(os.getenv("SUPA_MP3_TIMEOUT", "60"))
_SUPA_FETCH_RETRIES = int(os.getenv("SUPA_MP3_RETRIES", "3"))
_SUPA_BACKOFF       = float(os.getenv("SUPA_MP3_BACKOFF", "1.8"))

_play_lock = asyncio.Lock()

def _looks_like_mp3(b: bytes) -> bool:
    # ID3 tag or MPEG frame sync
    return b.startswith(b"ID3") or (len(b) > 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0)


def canon_lang(code: str | None) -> str:
    c = (code or "en").strip().lower()
    return _LANG_MAP.get(c, "en")

def bucket_for(language: str, kind: Kind) -> str:
    lang = canon_lang(language)
    return BUCKETS.get(lang, BUCKETS["en"])[kind]

def key_for(kind: Kind, filename: str | None) -> Optional[str]:
    if not filename:
        return None
    return f"{AUDIO_PREFIXES[kind]}/{filename}"

def build_intro_filename(decade: str, genre: str, rank: int) -> str:
    return f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{rank:02}.mp3"

def build_detail_filename(spotify_track_id: str | None) -> Optional[str]:
    return f"{spotify_track_id}.mp3" if spotify_track_id else None

def build_artist_filename(spotify_artist_id: str | None) -> Optional[str]:
    return f"{spotify_artist_id}.mp3" if spotify_artist_id else None
async def safe_play(kind: str, bucket: str, key: str) -> bool:
    """
    Robust MP3 playback from Supabase with HEAD probe, GET retries, and
    sequential playback (locked). Returns True on success.
    kind: "Intro" | "Detail" | "Artist"
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
            logger.warning("❌ %s MP3 missing: %s/%s (status=%s)", kind, bucket, key, head.status_code)
            return False
    except Exception as e:
        logger.debug("HEAD failed for %s %s/%s: %s (will try GET)", kind, bucket, key, e)

    last_err = None

    async with _play_lock:  # 👈 ensure one-at-a-time playback
        for attempt in range(1, _SUPA_FETCH_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                # Download bytes (streaming)
                async with httpx.AsyncClient(timeout=_SUPA_FETCH_TIMEOUT) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    b = await resp.aread()

                size = len(b or b"")
                if size < 1024:
                    raise RuntimeError(f"Downloaded size too small: {size} bytes")
                if not _looks_like_mp3(b):
                    raise RuntimeError("Not an MP3 (bad header)")

                # NEW (handles both async and sync play_mp3)
                res = play_mp3(b, block=True, diagnostics=False)
                rc = await res if inspect.iscoroutine(res) else res

                dt = time.perf_counter() - t0
                if rc == 0:
                    logger.debug("✅ %s MP3 played in %.2fs (%s/%s) [bytes=%d, rc=%d]",
                                kind, dt, bucket, key, size, rc)
                    return True

                last_err = f"ffplay rc={rc}"
                logger.warning("⚠️ %s play failed (attempt %d/%d) rc=%s %s/%s",
                               kind, attempt, _SUPA_FETCH_RETRIES, rc, bucket, key)

            except httpx.ReadTimeout as e:
                last_err = e
                logger.warning("⏳ %s GET timeout (attempt %d/%d) %s/%s",
                               kind, attempt, _SUPA_FETCH_RETRIES, bucket, key)
            except Exception as e:
                last_err = e
                logger.warning("⚠️ %s MP3 exception (attempt %d/%d) %s/%s: %s",
                               kind, attempt, _SUPA_FETCH_RETRIES, bucket, key, e)

            if attempt < _SUPA_FETCH_RETRIES:
                await asyncio.sleep(_SUPA_BACKOFF ** attempt)

    logger.error("❌ %s MP3 gave up after %d attempts: %s/%s :: %s",
                 kind, _SUPA_FETCH_RETRIES, bucket, key, last_err)
    return False

def _log_one_line(label: str, text: str | None, file: str | None):
    if not text:
        return
    # collapse all whitespace/newlines to single spaces and emit a single log line
    one_line = " ".join(text.split())
    suffix = f": {file}" if file else ":"
    logger.info("%s%s %s", label, suffix, one_line)

def log_narration_texts(
    *,
    intro: str | None,
    detail: str | None,
    artist: str | None,
    intro_file: str | None = None,
    detail_file: str | None = None,
    artist_file: str | None = None,
) -> None:
    _log_one_line("📣 INTRO TEXT",  intro,  intro_file)
    _log_one_line("📝 DETAIL TEXT", detail, detail_file)
    _log_one_line("👤 ARTIST TEXT", artist, artist_file)
