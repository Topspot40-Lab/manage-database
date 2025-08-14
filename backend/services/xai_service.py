# ─────────────────────────────────────────────────────────────────────────────
# 📦 Imports
# ─────────────────────────────────────────────────────────────────────────────
import os
import json
import logging
from dotenv import load_dotenv

from backend.config import TEST_JSON_DIR
from backend.utils.mode_utils import ModeFlag
from backend.utils.track_filters import validate_tracks
from backend.services.xai_prompt_builder import build_track_prompt
from backend.services.xai_response_handler import parse_and_filter_tracks
from backend.services.xai_api_client import fetch_xai_tracks


# ─────────────────────────────────────────────────────────────────────────────
# 🔐 Environment & Config
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/track_schema.json")

with open(SCHEMA_PATH, "r") as f:
    TRACK_SCHEMA = json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 🪵 Logger Setup
# ─────────────────────────────────────────────────────────────────────────────
def get_step_logger(name: str, fallback: str = "STEP_1") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.level == logging.NOTSET:
        return logging.getLogger(fallback)
    return logger

logger = logging.getLogger(__name__)
logger_step1a = get_step_logger("STEP_1.A")
logger_step1b = get_step_logger("STEP_1.B")
logger_step1c = get_step_logger("STEP_1.C")
logger_step1  = get_step_logger("STEP_1")   # 🔄 fallback


# ─────────────────────────────────────────────────────────────────────────────
# 🎛️ Track Formatter Utilities
# ─────────────────────────────────────────────────────────────────────────────
def format_mode_flag(flag):
    try:
        name = ModeFlag(flag).name.lower()
    except (ValueError, AttributeError):
        name = str(flag).lower()
    return {
        "solo": " solo",
        "duet": "→→  duet",
        "featured": "→→→ feat",
        "group": "→→→→ group"
    }.get(name, f" {name[:10].strip()}")

def format_track_list(
    tracks,
    fields=("rank", "track_name", "artist_name", "mode_flag"),
    min_widths=None,
    max_widths=None,
):
    """
    Formats a table of tracks. Robust to missing keys / new field names and generators.
    """
    # Make sure we can iterate twice
    tracks = list(tracks or [])
    if not tracks:
        return "⚠️ No tracks to display."

    # Map of canonical field -> list of possible aliases present in data
    aliases = {
        "rank": ["rank", "position", "idx"],
        "track_name": ["track_name", "trackName", "title", "track"],
        "artist_name": ["artist_name", "artistName", "artist", "main_artist", "artist_display_name"],
        "mode_flag": ["mode_flag", "modeFlag", "mode", "mode_flag_detail"],
    }

    def get_value(item, canon_key):
        for k in aliases.get(canon_key, [canon_key]):
            if k in item and item[k] is not None:
                return str(item[k])
        return ""

    # Defaults & bounds
    min_widths = min_widths or {"rank": 4, "track_name": 16, "artist_name": 16, "mode_flag": 8}
    max_widths = max_widths or {"rank": 6, "track_name": 48, "artist_name": 48, "mode_flag": 20}

    # Compute dynamic widths from data (respecting min/max)
    widths = {}
    for f in fields:
        # header width at least the field label length
        hdr = f
        max_len = len(hdr)
        for it in tracks:
            v = get_value(it, f)
            if f == "mode_flag":
                v = format_mode_flag(v) if v else ""
            max_len = max(max_len, len(v))
        lo = min_widths.get(f, 8)
        hi = max_widths.get(f, 32)
        widths[f] = max(lo, min(hi, max_len))

    # Build header/rows
    header = " | ".join(f"{f:<{widths[f]}}" for f in fields)
    separator = "-" * len(header)
    lines = ["🎧 Track summary:", header, separator]

    for it in tracks:
        row = []
        for f in fields:
            v = get_value(it, f)
            if f == "mode_flag":
                v = format_mode_flag(v) if v else ""
            row.append(v.ljust(widths[f])[:widths[f]])
        lines.append(" | ".join(row))

    return "\n".join(lines)

def safe_trim(text: str, width: int) -> str:
    return (text or "")[: width - 1] + "…" if text and len(text) > width else (text or "")

def format_detail_track_list(tracks) -> str:
    """
    Return a 2-section track summary:
    1) Raw Artist Assignment
    2) Mode & Display Info
    Robust to missing/renamed keys and None values.
    """
    tracks = list(tracks or [])
    if not tracks:
        return "⚠️ No tracks to display."

    # --- Aliases so we survive schema drift ---
    A = {
        "rank": ["rank", "position", "idx"],
        "track_name": ["track_name", "trackName", "title", "track"],
        "main_artist_name": ["main_artist_name", "mainArtistName", "main_artist", "mainArtist", "primary_artist"],
        "featured_artist_name": ["featured_artist_name", "featuredArtistName", "featured_artist", "featuredArtist", "feat_artist"],
        "artist_name": ["artist_name", "artistName", "artist", "group_name"],
        "artist_display_name": ["artist_display_name", "artistDisplayName", "display_name", "displayName", "artist_pretty"],
        "mode_flag": ["mode_flag", "modeFlag", "mode"],
        "mode_flag_detail": ["mode_flag_detail", "modeFlagDetail", "mode_detail", "modeDetail"],
    }

    def getv(item, canon_key, default=""):
        for k in A.get(canon_key, [canon_key]):
            v = item.get(k)
            if v is not None:
                return str(v)
        return default

    def trim(s, n):
        s = (s or "").strip()
        return s if len(s) <= n else s[: max(0, n - 1)].rstrip() + "…"

    # ---------- Section 1 ----------
    sect1_cols = (
        ("rank", 4, 6),
        ("track_name", 24, 48),
        ("main_artist_name", 18, 40),
        ("featured_artist_name", 18, 40),
    )

    def compute_widths(cols):
        widths = {}
        for key, lo, hi in cols:
            header_len = len(key)
            max_len = header_len
            for t in tracks:
                v = getv(t, key)
                max_len = max(max_len, len(v))
            widths[key] = max(lo, min(hi, max_len))
        return widths

    w1 = compute_widths(sect1_cols)

    header1 = " | ".join(f"{k:<{w1[k]}}" for k, _, _ in sect1_cols)
    lines = ["🎧 Section 1 — Raw Artist Assignment", header1, "-" * len(header1)]
    for t in tracks:
        row = [
            f"{getv(t,'rank'):<{w1['rank']}}",
            f"{trim(getv(t,'track_name'), w1['track_name']):<{w1['track_name']}}",
            f"{trim(getv(t,'main_artist_name'), w1['main_artist_name']):<{w1['main_artist_name']}}",
            f"{trim(getv(t,'featured_artist_name'), w1['featured_artist_name']):<{w1['featured_artist_name']}}",
        ]
        lines.append(" | ".join(row))

    lines.append("")

    # ---------- Section 2 ----------
    sect2_cols = (
        ("rank", 4, 6),
        ("artist_name", 18, 40),
        ("artist_display_name", 24, 48),
        ("mode_flag", 8, 16),
        ("mode_flag_detail", 24, 80),
    )

    w2 = compute_widths(sect2_cols)

    header2 = " | ".join(f"{k:<{w2[k]}}" for k, _, _ in sect2_cols)
    lines.append("🎧 Section 2 — Mode & Display Info")
    lines.append(header2)
    lines.append("-" * len(header2))

    for t in tracks:
        mode = getv(t, "mode_flag")
        try:
            mode_fmt = format_mode_flag(mode) if mode else ""
        except Exception:
            mode_fmt = mode or ""

        row = [
            f"{getv(t,'rank'):<{w2['rank']}}",
            f"{trim(getv(t,'artist_name'), w2['artist_name']):<{w2['artist_name']}}",
            f"{trim(getv(t,'artist_display_name'), w2['artist_display_name']):<{w2['artist_display_name']}}",
            f"{mode_fmt:<{w2['mode_flag']}}",
            f"{trim(getv(t,'mode_flag_detail'), w2['mode_flag_detail']):<{w2['mode_flag_detail']}}",
        ]
        lines.append(" | ".join(row))

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 🧠 XAI Track Retrieval
# ─────────────────────────────────────────────────────────────────────────────
def get_top_tracks_from_xai(decade, genre, language, num_tracks, test_file_number=0):
    # buffer_size = 0 if test_file_number > 0 else max(0, round(num_tracks * 0.15))
    buffer_size = 0
    total_requested = num_tracks + buffer_size

    logger_step1a.debug(
        f"[STEP_1.A] test_file_number={test_file_number}, num_tracks={num_tracks}, buffer={buffer_size}, "
        f"total_requested={total_requested}, decade={decade}, genre={genre}, language={language}"
    )

    prompt = build_track_prompt(decade, genre, total_requested, language, buffer_size)
    logger_step1b.debug("[STEP_1.B] Requesting top tracks from XAI...")
    tracks = []

    if test_file_number > 0:
        test_file_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
        logger_step1b.debug(f"[STEP_1.B] [TEST] Using {test_file_path}")
        try:
            with open(test_file_path, "r", encoding="utf-8") as test_file:
                test_json = json.load(test_file)
            raw_tracks = test_json.get("tracks", [])
            logger_step1b.debug(f"[STEP_1.B] [TEST] Loaded {len(raw_tracks)} tracks.")

            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), total_requested, is_test_mode=True)

            if logger_step1b.isEnabledFor(logging.INFO) or logger_step1.isEnabledFor(logging.INFO):
                # logger_step1b.info(format_track_list(tracks))
                logger_step1b.info(format_detail_track_list(tracks))

            # Stub Spotify data for consistency
            for t in tracks:
                rank = t.get("rank", 0)
                t["spotify_data"] = {
                    "spotify_track_id": f"test_track_{rank}",
                    "artist_id": f"test_artist_{rank}",
                    "duration_ms": 180000,
                    "popularity": 55,
                    "album_artwork": None,
                    "artist_artwork": None,
                    "artist_description": None,
                    "featured_artist_id": None,
                    "featured_artist_name": None,
                    "not_on_spotify": False,
                }

        except Exception as e:
            logger_step1b.error(f"[ERROR] Failed to load test file: {e}")

    else:
        content = fetch_xai_tracks(prompt, test_file_number=test_file_number)

        if isinstance(content, list):
            logger_step1b.debug("[STEP_1.B] ➤ content is a list — using as-is")
            logger_step1b.debug(f"[XAI] Received {len(content)} tracks.{content}")
            tracks = content

        elif isinstance(content, str):
            logger_step1b.debug("[STEP_1.B] ➤ content is a str — attempting to parse JSON string")
            tracks = parse_and_filter_tracks(content, num_tracks, is_test_mode=False)

        elif isinstance(content, dict):
            logger_step1b.debug("[STEP_1.B] ➤ content is a dict — extracting 'tracks' key")
            raw_tracks = content.get("tracks", [])
            if not isinstance(raw_tracks, list):
                raise ValueError("Expected 'tracks' to be a list.")
            logger_step1b.debug(f"[XAI] Extracted {len(raw_tracks)} tracks.")
            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), total_requested, is_test_mode=False)

        else:
            logger_step1b.error(f"[STEP_1.B] ❌ content is unexpected type: {type(content)}")
            raise TypeError(f"Unexpected content type: {type(content)}")

        if tracks:
            logger_step1b.debug(f"[XAI] Received {len(content)} tracks.{tracks}")
            logger_step1b.info("🎧 [STEP_1.B] XAI Track summary:\n" + format_track_list(tracks))
            logger_step1b.info(format_detail_track_list(tracks))
        else:
            logger_step1b.debug("⚠️ No tracks returned.")

    # Final cleanup
    valid_tracks = validate_tracks(tracks)

    if logger_step1c.isEnabledFor(logging.DEBUG):
        logger_step1c.debug("🎧 [STEP_1.C] Final validated track summary:\n" + format_track_list(valid_tracks))

    logger_step1c.debug(
        f"[STEP_1.C] [CLEANUP] {len(valid_tracks)} valid tracks from {len(tracks)} total, "
        f"returning {len(valid_tracks)} cleaned from {total_requested} requested."
    )

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": valid_tracks
    }
