# backend/services/xai_artist_detail.py

import json
import logging
from sqlmodel import Session, select
from sqlalchemy import or_
from backend.models.dbmodels import Artist
from backend.services.xai_common import query_xai

logger = logging.getLogger("STEP_9.ArtistDetail")

def get_artist_descriptions_from_xai(artists, language: str, batch_size: int = 25):
    """
    Calls xAI in smaller batches to generate artist descriptions safely.
    Each result: {"artist_name": str, "artist_description": str}
    """
    seen_artists = {}
    unique_input = []
    for a in artists:
        name = (a.get("artist_name") or "").strip()
        if name and name.lower() not in seen_artists:
            seen_artists[name.lower()] = True
            unique_input.append({"artist_name": name})

    if not unique_input:
        logger.warning("🚫 No unique artists found for description.")
        return []

    all_results: list[dict] = []

    # ─────────────────────────────────────────────────────────────
    # Process in manageable chunks (avoid token / timeouts)
    # ─────────────────────────────────────────────────────────────
    for i in range(0, len(unique_input), batch_size):
        batch = unique_input[i:i + batch_size]
        logger.info(f"🎨 Sending artist batch {i//batch_size + 1} ({len(batch)} artists) to xAI...")

        prompt = (
            f"Write artist descriptions in {language}.\n"
            "For each artist below, output a JSON array where each item has:\n"
            "  - artist_name\n"
            "  - artist_description (2–3 sentences about career, genre, legacy, and influence).\n"
            "Avoid listing songs unless iconic. Be concise and factual.\n\n"
            f"Artists:\n{json.dumps(batch, indent=2)}\n\n"
            "Output ONLY valid JSON (no markdown or commentary)."
        )

        raw = query_xai(prompt)
        if not raw:
            logger.warning(f"⚠️ Empty response from xAI for batch {i//batch_size + 1}")
            continue

        # Debug preview
        logger.debug("🪶 Raw xAI content (first 300 chars): %s", str(raw)[:300])

        # Try to parse JSON directly if query_xai() didn't already
        parsed = None
        if isinstance(raw, list):
            parsed = raw
        else:
            try:
                parsed = json.loads(raw)
            except Exception as ex:
                logger.error("⚠️ Failed to parse xAI response (batch %d): %s", i//batch_size + 1, ex)
                continue

        # Validate and collect
        for r in parsed or []:
            name = (r.get("artist_name") or "").strip()
            desc = (r.get("artist_description") or "").strip()
            if name and desc:
                all_results.append({"artist_name": name, "artist_description": desc})
            else:
                logger.warning(f"⚠️ Invalid artist entry skipped: {r}")

    logger.info(f"✅ xAI generated {len(all_results)} artist descriptions in total.")
    return all_results

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
