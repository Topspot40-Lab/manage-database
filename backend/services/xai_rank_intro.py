import json
import logging
from backend.services.xai_common import query_xai

logger = logging.getLogger("STEP_9.RankIntro")

def get_rank_intros_from_xai(tracks, language, decade, genre):
    """
    Updates each track in-place with a generated 'intro' string.
    Returns the original list with intros added to each track.
    """
    batch_size = 10
    total = len(tracks)

    for batch_start in range(0, total, batch_size):
        batch = tracks[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        logger.debug(f"📦 [Batch {batch_num}] Creating rank intros for tracks {batch_start + 1} to {batch_start + len(batch)}")

        formatted_input = []
        for t in batch:
            # ... inside the for t in batch: loop
            entry = {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "track_name": t.get("track_name"),
                "artist_name": t.get("artist_name"),
                "album_name": t.get("album_name"),
                "year_released": t.get("year_released"),  # ✅ add this
                "mode_flag_detail": t.get("mode_flag_detail"),
            }

            formatted_input.append(entry)

        # ... when building `prompt`
        prompt = (
            f"Generate the following fields in {language}: intro. "
            "• 'intro' must be one or two lively sentences (max 35 words). "
            "Include rank, decade, genre, track_name, artist_name, and album_name. "
            "If year_released is provided, include the release year succinctly (e.g., 'released in 1961'). "
            "If album_name is available, clearly name it (e.g., 'from the album Hello Walls'). "
            "If mode_flag_detail is present, incorporate it naturally. "
            "Vary the tone: sometimes playful, sometimes dramatic, sometimes trivia-style. "
            "Avoid starting more than two intros in a row with the same word. "
            "Do not guess missing values; omit any field that is null.\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        responses = query_xai(prompt)
        if not responses:
            logger.warning(f"⚠️ Batch {batch_num} failed or returned empty.")
            continue

        for i, desc in enumerate(responses):
            track = tracks[batch_start + i]
            intro = desc.get("intro", "")
            track["_xai_intro"] = intro  # or return it separately

            if intro:
                logger.debug(f"🟢 Rank {track.get('rank')} intro: {intro}")
            else:
                logger.warning(f"⚠️ Rank {track.get('rank')} intro missing or empty")

    return {"tracks": tracks}
