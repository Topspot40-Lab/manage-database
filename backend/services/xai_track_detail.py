import json
import logging
from sqlmodel import Session, select
from backend.models import Track
from backend.services.xai_common import query_xai
from sqlalchemy import or_
from sqlalchemy.orm import selectinload  # ✅ ADD THIS

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
                "album_name": t.get("album_name")
                # "mode_flag_detail": t.get("mode_flag_detail")
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
            logger.debug(f"🟣 Detail for track '{track.get('track_name')}' by {track.get('artist_name')}:\n{detail}")


def regenerate_missing_track_details(db: Session, language: str = "English") -> int:
    """
    Finds all tracks missing the 'detail' field and regenerates them using XAI,
    saving the updated details back into the database.
    """
    logger.info("🔁 Regenerating missing track detail text from Supabase...")

    # ✅ Step 1: Query with eager-loading for artist
    statement = select(Track).options(selectinload(Track.artist)).where(
        or_(
            Track.detail.is_(None),
            Track.detail == ""
        )
    )
    results = db.exec(statement).all()
    if not results:
        logger.info("✅ No tracks with missing detail.")
        return 0

    logger.info(f"🧠 Found {len(results)} tracks missing detail. Sending to XAI...")

    # Step 2: Prepare input for XAI
    track_dicts = []
    for track in results:
        if not track.artist:
            logger.warning(f"❓ Track '{track.track_name}' is missing an artist relationship.")

        track_dicts.append({
            "track_name": track.track_name,
            "artist_name": track.artist.artist_name if track.artist else "Unknown",
            "album_name": track.album_name,
            # "mode_flag_detail": track.mode_flag_detail,
        })

    # Step 3: Generate new 'detail' text
    get_track_details_from_xai(track_dicts, language=language)

    # Step 4: Save generated text back to the database
    for i, track in enumerate(results):
        new_detail = track_dicts[i].get("detail")
        if new_detail:
            track.detail = new_detail
            logger.debug(f"📝 Updated detail for: {track.track_name} by {track.artist.artist_name if track.artist else 'Unknown'}")

    db.commit()
    logger.info("✅ All missing details regenerated and saved.")
    return len(results)
