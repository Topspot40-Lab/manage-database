# backend/services/xai_descriptions.py

import json, requests
from typing import Optional

from backend.config import (
    ENABLE_TRACK_DESCRIPTION,
    ENABLE_RANK_INTRO,
    ENABLE_ARTIST_DESCRIPTION,
    XAI_API_KEY,
    XAI_API_URL,
)
from backend.utils.logger_factory import get_step_logger

logger_step2 = get_step_logger("STEP_2")      # General Step 2
logger_intro = get_step_logger("STEP_2.A")    # Rank Intro Text
logger_detail = get_step_logger("STEP_2.B")   # Track Detail Text
logger_artist = get_step_logger("STEP_2.C")   # Artist Detail Text


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

        formatted_input = [
            {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "trackName": t.get("trackName"),
                "artistName": t.get("artistName"),
            }
            for t in batch
        ]

        # requested_fields, instructions = [], []
        # --------------------------------------------------------------
        # Build the “instructions” list more descriptively
        # --------------------------------------------------------------
        requested_fields, instructions = [], []

        if ENABLE_RANK_INTRO:
            requested_fields.append("intro")
            instructions.append(
                # Short, punchy opener
                "• 'intro' must be ONE lively sentence (max 25 words). "
                "Include rank, decade, genre, track name, and artist name. "
                "Vary the tone: sometimes playful, sometimes dramatic, sometimes trivia‑style. "
                "Avoid starting more than two intros in a row with the same word."
            )

        if ENABLE_TRACK_DESCRIPTION:
            requested_fields.append("detail")
            instructions.append(
                # Rich Casey‑Kasem‑style narrative
                "• 'detail' must be 2‑4 sentences (≈80‑120 words) in a warm Casey Kasem style. "
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

            batch_descriptions = json.loads(content)
            for i, desc in enumerate(batch_descriptions):
                tracks[batch_start + i].update(desc)
                rank = tracks[batch_start + i].get("rank")
                intro = desc.get("intro")
                detail = desc.get("detail")

                logger_step2.debug(
                    f"✅ [STEP_2] Rank {rank}: "
                    f"intro={'✔️' if intro else '❌'}, "
                    f"detail={'✔️' if detail else '❌'}, "
                    f"artist={'✔️' if tracks[batch_start + i].get('artist_description') else '❌'}"
                )

                if intro:
                    logger_intro.debug(f"🅰️ Rank {rank} intro: {intro.strip()}")
                if detail:
                    logger_detail.debug(f"🅱️ Rank {rank} detail:\n{detail.strip()}")


        except Exception as e:
            logger_step2.error(f"[XAI ERROR] Batch {batch_num}: {e}")
            continue

    # -- after finishing all batches --
    enrich_tracks_with_artist_descriptions(tracks, language)


    logger_step2.info("✅ STEP 2 complete.")
    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }


def get_artist_description(artist_name: str, language: str = "English") -> Optional[str]:
    if not ENABLE_ARTIST_DESCRIPTION:
        logger_step2.debug(f"[SKIP] Artist description disabled for {artist_name}.")
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

    logger_artist.debug(f"🎤 Requesting bio for: {artist_name}")

    try:
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if not content.strip():
            logger_step2.warning(f"[EMPTY] No content returned for: {artist_name}")
            return f"(No description found for {artist_name})"

        logger_artist.debug(f"🎤 Full bio for {artist_name}:\n{content.strip()}")

        return content.strip()

    except requests.exceptions.HTTPError as e:
        logger_step2.error(f"[HTTP ERROR] {e}")
        return f"(HTTP error fetching description for {artist_name})"

    except Exception as e:
        logger_step2.error(f"[ERROR] Unexpected issue: {e}")
        return f"(Unexpected error fetching description for {artist_name})"


# ─────────────────────────────────────────────────────────────────────────────
# 🆕  STEP‑2D  ─ Fetch & attach artist descriptions
# -----------------------------------------------------------------------------


def enrich_tracks_with_artist_descriptions(tracks: list[dict], language: str) -> None:
    """
    Mutates `tracks` in place: adds 'artist_description' to each track.
    Only runs if ENABLE_ARTIST_DESCRIPTION = True.
    """

    if not ENABLE_ARTIST_DESCRIPTION:
        logger_step2.info("🎤 [STEP_2D] Artist‑description enrichment disabled.")
        return

    # 1️⃣ Build a set of unique artist names that still need a bio
    unique_artists: set[str] = {
        t.get("artistName") for t in tracks
        if t.get("artistName") and not t.get("artist_description")
    }

    if not unique_artists:
        logger_step2.debug("🎤 [STEP_2] No missing artist descriptions. Skipping.")
        return

    logger_step2.debug(f"🎤 [STEP_2] Fetching bios for {len(unique_artists)} artists…")

    # 2️⃣ Fetch bios with per‑artist caching to avoid duplicates
    bio_cache: dict[str, str] = {}

    for artist in sorted(unique_artists):
        bio = bio_cache.get(artist)
        if bio is None:
            bio = get_artist_description(artist, language)  # already logs internally
            bio_cache[artist] = bio

        for t in tracks:
            if t.get("artistName") == artist:
                t["artist_description"] = bio

        logger_artist.debug(
            f"🎙️  Attached bio for '{artist}' to "
            f"{sum(1 for t in tracks if t.get('artistName') == artist)} track(s)."
        )

    logger_step2.debug("🎤 [STEP_2.C] Artist bios attached.\n")


# ─────────────────────────────────────────────────────────────────────────────
# 🎯 Call this at the very end of get_track_descriptions_from_xai()
# ─────────────────────────────────────────────────────────────────────────────
