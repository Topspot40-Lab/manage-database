# backend/services/xai_track_detail.py

import json
import logging
from backend.services.xai_common import query_xai

logger = logging.getLogger("STEP_9.TrackDetail")

def get_track_details_from_xai(tracks, language):

    """
    Adds 'detail' field to each track with 2–4 sentences of Casey Kasem-style storytelling.
    """
    batch_size = 10
    total = len(tracks)

    for batch_start in range(0, total, batch_size):
        batch = tracks[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        logger.debug(f"📦 [Batch {batch_num}] Creating track details for tracks {batch_start + 1} to {batch_start + len(batch)}")

        formatted_input = []
        for t in batch:
            formatted_input.append({
                "track_name": t.get("track_name"),
                "artist_name": t.get("artist_name"),
                "album_name": t.get("album_name"),
                "mode_flag_detail": t.get("mode_flag_detail")
            })

        prompt = (
            f"Generate the following fields in {language}: detail. "
            "• 'detail' must be 2–4 warm and engaging sentences (≈80–120 words) written in the style of Casey Kasem. "
            "⚠️ Do NOT repeat any info from the intro — including rank, decade, genre, track_name, artist_name, or album_name. "
            "Instead, dive into songwriting origins, chart milestones, producer quirks, recording sessions, or cultural impact. "
            "You can include trivia, fun facts, or behind‑the‑scenes drama. "
            "Mention songwriters, studio, or instrumentation if it adds flavor. "
            "Wrap it up with a radio-style flourish.\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        responses = query_xai(prompt)
        if not responses:
            logger.warning(f"⚠️ Batch {batch_num} failed or returned empty.")
            continue

        for i, resp in enumerate(responses):
            track = tracks[batch_start + i]
            detail = resp.get("detail")
            track["detail"] = detail
            logger.debug(f"🟣 Rank {track.get('rank')} detail:\n{detail}")
