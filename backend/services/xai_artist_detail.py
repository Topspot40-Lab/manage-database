# backend/services/xai_artist_detail.py

import json
import logging
from sqlmodel import Session, select
from sqlalchemy import or_
from backend.models import Artist
from backend.services.xai_common import query_xai

logger = logging.getLogger("STEP_9.ArtistDetail")


def get_artist_descriptions_from_xai(artists, language):
    """
    Returns a list of artist descriptions (1 per unique artist).
    Each item has: artist_name, artist_description.
    """
    seen_artists = {}
    unique_input = []

    for a in artists:
        name = a.get("artist_name", "").strip()
        if name and name.lower() not in seen_artists:
            seen_artists[name.lower()] = True
            unique_input.append({"artist_name": name})

    if not unique_input:
        logger.warning("🚫 No unique artists found for description.")
        return []

    prompt = (
        f"Generate the following fields in {language}: artist_description. "
        "• For each artist, write 2–3 sentences about their career, legacy, genre influence, or signature style. "
        "You may include notable awards, famous songs, cultural impact, or little-known facts.\n"
        f"Artists:\n{json.dumps(unique_input, indent=2)}"
    )

    responses = query_xai(prompt)
    if not responses:
        logger.warning("⚠️ Artist description query returned no results.")
        return []

    artist_descriptions = []

    for resp in responses:
        name = resp.get("artist_name", "").strip()
        desc = resp.get("artist_description")
        if name and desc:
            logger.debug(f"🎙️ Artist '{name}' description added.")
            artist_descriptions.append({
                "artist_name": name,
                "artist_description": desc
            })
        else:
            logger.warning(f"❌ Missing description for response: {resp}")

    return artist_descriptions


def regenerate_missing_artist_descriptions(db: Session, language: str = "English") -> int:
    """
    Finds all artists missing descriptions and regenerates them using XAI,
    then saves them back into the database.
    """
    logger.info("🔁 Regenerating missing artist descriptions from Supabase...")

    # Step 1: Query all artists with missing descriptions
    statement = select(Artist).where(
        or_(
            Artist.artist_description.is_(None),
            Artist.artist_description == ""
        )
    )
    artists = db.exec(statement).all()

    if not artists:
        logger.info("✅ No missing artist descriptions found.")
        return 0

    logger.info(f"🧠 Found {len(artists)} artists missing descriptions. Sending to XAI...")

    # Step 2: Prepare input for XAI
    artist_dicts = [{"artist_name": artist.artist_name} for artist in artists]

    # Step 3: Generate new descriptions
    results = get_artist_descriptions_from_xai(artist_dicts, language)

    # Step 4: Map results and update DB
    name_to_artist = {a.artist_name.lower(): a for a in artists}
    updated_count = 0

    for item in results:
        name = item["artist_name"].lower()
        desc = item["artist_description"]
        artist = name_to_artist.get(name)
        if artist:
            artist.artist_description = desc
            updated_count += 1
            logger.debug(f"📝 Updated description for artist: {artist.artist_name}")

    db.commit()
    logger.info(f"✅ {updated_count} artist descriptions updated.")
    return updated_count
