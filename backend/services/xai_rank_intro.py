import json
import logging
from backend.services.xai_common import query_xai
from backend.utils.validation import is_valid_intro

logger = logging.getLogger("STEP_9.RankIntro")

def get_rank_intros_from_xai(tracks, language, decade, genre):
    """
    Returns a list of intro summaries for each track, mapped by track_id and rank.
    Each item includes track_id, rank, genre, decade, and the generated intro text.
    """
    batch_size = 10
    total = len(tracks)
    all_intros = []

    for batch_start in range(0, total, batch_size):
        batch = tracks[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        logger.debug(f"📦 [Batch {batch_num}] Creating rank intros for tracks {batch_start + 1} to {batch_start + len(batch)}")

        formatted_input = []
        for t in batch:
            entry = {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "track_name": t.get("track_name"),
                "artist_name": t.get("artist_name"),
                "album_name": t.get("album_name"),
                "mode_flag_detail": t.get("mode_flag_detail"),
            }
            formatted_input.append(entry)

        prompt = (
            f"Generate the following fields in {language}: intro. "
            "• 'intro' must be one or two lively sentences (max 35 words). "
            "Include rank, decade, genre, track_name, artist_name, and album_name. "
            "If album_name is available, clearly name it (e.g., 'from the album Hello Walls'). "
            "If mode_flag_detail is present, incorporate it naturally. "
            "Vary the tone: sometimes playful, sometimes dramatic, sometimes trivia-style. "
            "Avoid starting more than two intros in a row with the same word.\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        responses = query_xai(prompt)
        if not responses:
            logger.warning(f"⚠️ Batch {batch_num} failed or returned empty.")
            continue

        for i, desc in enumerate(responses):
            track = tracks[batch_start + i]
            intro = desc.get("intro")
            track_id = track.get("spotify_track_id")

            entry = {
                "track_id": track_id,
                "rank": track.get("rank"),
                "intro": intro,
                "genre": genre,
                "decade": decade,
            }
            all_intros.append(entry)

            # 🔍 Optional validation
            if intro and not is_valid_intro(
                intro,
                track_name=track.get("track_name", ""),
                artist_name=track.get("artist_name", ""),
                genre=genre,
                decade=decade,
                rank=track.get("rank")
            ):
                logger.warning(f"⚠️ Rank {track.get('rank')} intro failed validation:\n{intro}")
            else:
                logger.debug(f"🟢 Rank {track.get('rank')} intro: {intro}")

    return all_intros
