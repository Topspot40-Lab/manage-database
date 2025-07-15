# backend/services/xai_descriptions.py
from backend.utils.track_helpers import normalize_track_keys
import json, requests
import re
from typing import Optional
from backend.utils.json_helpers import normalize_text

from backend.config import (
    ENABLE_TRACK_DESCRIPTION,
    ENABLE_RANK_INTRO,
    ENABLE_ARTIST_DESCRIPTION,
    XAI_API_KEY,
    XAI_API_URL,
)
from backend.utils.logger_factory import get_step_logger

logger_step2 = get_step_logger("STEP_2")        # General Step 2
logger_step2a = get_step_logger("STEP_2.A")     # ✍️ Rank Intro Text
logger_step2b = get_step_logger("STEP_2.B")     # 🧪 Track Detail Text
logger_step2c = get_step_logger("STEP_2.C")     # 🎙️ Artist Bio Text



def get_track_descriptions_from_xai(track_data, language, decade, genre):
    if not ENABLE_TRACK_DESCRIPTION and not ENABLE_RANK_INTRO:
        logger_step2.info("🧮 Skipping STEP 2 description generation — no tokens used.")
        return {
            "language": language,
            "decade": decade,
            "genre": genre,
            "tracks": track_data.get("tracks", track_data)
        }

    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])
    total = len(tracks)
    batch_size = 10

    logger_step2.debug(f"✍️ [STEP_2]: Enriching {total} tracks with XAI descriptions (batch={batch_size})")

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = tracks[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        logger_step2.debug(f"   • [STEP_2] Batch {batch_num}: tracks {batch_start+1}-{batch_end}")

        formatted_input = []
        for t in batch:
            entry = {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "track_name": t.get("track_name"),
                "artist_name": t.get("artist_name"),
            }
            if t.get("mode_flag_detail"):
                entry["mode_flag_detail"] = t["mode_flag_detail"]
            formatted_input.append(entry)

        # requested_fields, instructions = [], []
        # --------------------------------------------------------------
        # Build the “instructions” list more descriptively
        # --------------------------------------------------------------
        requested_fields, instructions = [], []

        if ENABLE_RANK_INTRO:
            requested_fields.append("intro")
            instructions.append(
                "• 'intro' must be ONE lively sentence (max 30 words). "
                "Include rank, decade, genre, track_name, and artist_name. "
                "If 'mode_flag_detail' is present, incorporate it naturally (e.g., 'joined by Willie Nelson'). "
                "Vary the tone: sometimes playful, sometimes dramatic, sometimes trivia‑style. "
                "Avoid starting more than two intros in a row with the same word."
            )

        if ENABLE_TRACK_DESCRIPTION:
            requested_fields.append("detail")
            instructions.append(
                # Rich Casey‑Kasem‑style narrative
                "• 'detail' must be 2‑4 sentences (≈80‑120 words) in a warm Casey Kasem style. "
                "⚠️ Do NOT repeat the rank, decade, genre, track name or artist name already stated in 'intro'. "
                "Focus on songwriting history, chart performance, producer/session tidbits, cultural impact, or a light humorous anecdote. "
                "Feel free to mention the songwriter(s), recording studio, or a quirky behind‑the‑scenes fact. "
                "End with a radio‑DJ‑flair tagline (e.g., '…and that’s the magic that still spins on turntables today!')."
            )

        prompt = (
            f"Generate the following fields in {language}: {', '.join(requested_fields)}. "
            + " ".join(instructions)
            + " Return only a valid JSON array.\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        payload = {
            "messages": [
                {"role": "system", "content": "You are an AI that returns valid JSON arrays only."},
                {"role": "user", "content": prompt}
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.3
        }

        headers = {
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(XAI_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            try:
                batch_descriptions = json.loads(content)
            except json.JSONDecodeError as e:
                logger_step2.error(
                    f"[XAI ERROR] JSON decode failed for Batch {batch_num}:\n{e}\nRaw content:\n{content}")
                continue

            for i, desc in enumerate(batch_descriptions):
                tracks[batch_start + i].update(desc)
                rank = tracks[batch_start + i].get("rank")
                intro = desc.get("intro")
                detail = desc.get("detail")

                track_name = tracks[batch_start + i].get("track_name", "")
                artist_name = tracks[batch_start + i].get("artist_name", "")

                if intro and not is_valid_intro(intro, track_name, artist_name):
                    logger_step2a.warning(f"⚠️ Rank {rank} — Intro missing required elements:\n{intro}")

                logger_step2.debug(
                    f"✅ [STEP_2] Rank {rank}: "
                    f"intro={'✔️' if intro else '❌'}, "
                    f"detail={'✔️' if detail else '❌'}, "
                    f"artist={'✔️' if tracks[batch_start + i].get('artist_description') else '❌'}"
                )

                artist_desc = tracks[batch_start + i].get("artist_description")

                log_lines = []
                if intro:
                    log_lines.append(f"🅰️ [STEP 2.A] Rank {rank} intro: {intro.strip()}")
                if detail:
                    log_lines.append(f"🅱️ [STEP 2.B] Rank {rank} detail:\n{detail.strip()}")
                if artist_desc:
                    log_lines.append(f"🎙️ [STEP 2.C] Rank {rank} — Artist: {artist_name}\n{artist_desc.strip()}")

                if log_lines:
                    logger_step2.debug("\n".join(log_lines))

        except Exception as e:
            logger_step2.error(f"[XAI ERROR] Batch {batch_num}: {e}")
            continue

    # -- after finishing all batches --
    enrich_tracks_with_artist_descriptions(tracks, language)

    # 🔍 Log artist descriptions after enrichment
    for t in tracks:
        artist_desc = t.get("artist_description")
        # print("Artist Description", artist_desc)
        if artist_desc:
            logger_step2c.debug(
                f"🎙️ Rank {t.get('rank')} — Artist: {t.get('artist_name')}\n{artist_desc.strip()}"
            )

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }


def is_valid_intro(intro: str, track_name: str, artist_name: str, genre: str = None, decade: str = None,
                   rank: int = None) -> bool:
    if not intro:
        return False

    intro_norm = normalize_text(intro)
    missing_fields = []

    # Check normalized fields
    if normalize_text(track_name) not in intro_norm:
        missing_fields.append("track_name")
    if normalize_text(artist_name) not in intro_norm:
        missing_fields.append("artist_name")
    if genre and normalize_text(genre) not in intro_norm:
        missing_fields.append("genre")
    if decade and str(decade) not in intro_norm:
        missing_fields.append("decade")

    # Accept either "rank 37", "#37", or "at 37"
    if rank is not None:
        if not re.search(rf"(rank|#|at)\s*{rank}\b", intro_norm):
            missing_fields.append(f"rank={rank}")

    if missing_fields:
        logger_step2a.debug(f"⚠️ Intro missing elements: {missing_fields}\n→ Intro: {intro}")
        return False

    return True


def get_artist_description(artist_name: str, language: str = "English") -> Optional[str]:
    if not ENABLE_ARTIST_DESCRIPTION:
        logger_step2c.debug(f"[SKIP] Artist description disabled for {artist_name}.")
        return None

    prompt = (
        f"Write a short artist biography in {language} for '{artist_name}'. "
        "Include nationality, genre, early story, key achievements, and trivia. "
        "Keep it short (2–3 sentences) with no formatting."
    )

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {"role": "system", "content": "You return plain-text artist bios only."},
            {"role": "user", "content": prompt}
        ],
        "model": "grok-2-latest",
        "stream": False,
        "temperature": 0.5
    }

    logger_step2c.debug(f"🎤 Requesting bio for: {artist_name}")

    try:
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if not content.strip():
            logger_step2c.warning(f"[EMPTY] No content returned for: {artist_name}")
            return f"(No description found for {artist_name})"

        logger_step2c.debug(f"🎤 Full bio for {artist_name}:\n{content.strip()}")

        return content.strip()

    except requests.exceptions.HTTPError as e:
        logger_step2c.error(f"[HTTP ERROR] {e}")
        return f"(HTTP error fetching description for {artist_name})"

    except Exception as e:
        logger_step2c.error(f"[ERROR] Unexpected issue: {e}")
        return f"(Unexpected error fetching description for {artist_name})"

# ─────────────────────────────────────────────────────────────────────────────
# 🆕  STEP‑2C  ─ Fetch & attach artist bios
# ----------------------------------------------------------------------------


def enrich_tracks_with_artist_descriptions(tracks: list[dict], language: str) -> None:
    """
    Adds `artist_description` to each track in-place.
    Runs only if ENABLE_ARTIST_DESCRIPTION = True.
    """

    if not ENABLE_ARTIST_DESCRIPTION:
        logger_step2c.info("🎤 [STEP_2C] Artist‑description enrichment disabled.")
        return

    # 🔄 Ensure we’re working with snake_case keys (`artist_name`)
    for i, t in enumerate(tracks):
        tracks[i] = normalize_track_keys(t, logger_step2c)  # harmless if already snake_case

    # 🗂️ Collect unique artists missing a bio
    unique_artists: set[str] = {
        t["artist_name"]
        for t in tracks
        if t.get("artist_name") and not (t.get("artist_description") or "").strip()
    }

    if not unique_artists:
        logger_step2c.debug("🎤 [STEP_2C] No missing artist descriptions. Skipping.")
        return

    logger_step2c.debug(f"🎯 [STEP_2C] Fetching bios for {len(unique_artists)} artists: {unique_artists}")

    # ️♻️ Simple in‑memory cache so we don’t hit XAI twice for the same artist
    bio_cache: dict[str, str] = {}

    for artist in sorted(unique_artists):
        # Fetch (or reuse) bio
        bio = bio_cache.get(artist)
        if bio is None:
            bio = get_artist_description(artist, language)  # already logs request/result
            bio_cache[artist] = bio

        # Attach to every track by that artist
        for t in tracks:
            if t.get("artist_name") == artist:
                t["artist_description"] = bio

        logger_step2c.debug(
            f"🎙️  Attached bio for '{artist}' to "
            f"{sum(1 for t in tracks if t.get('artist_name') == artist)} track(s)."
        )

    logger_step2c.debug("🎤 [STEP_2C] Artist bios attached.")
