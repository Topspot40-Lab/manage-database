# backend/services/xai_artist_detail.py

import json
import logging
from backend.services.xai_common import query_xai

logger = logging.getLogger("STEP_9.ArtistDetail")

def get_artist_descriptions_from_xai(tracks, language):
    """
    Returns a list of artist descriptions (1 per unique artist).
    Each item has: artist_name, artist_description.
    """
    seen_artists = {}
    unique_input = []

    for t in tracks:
        name = t.get("artist_name", "").strip()
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
