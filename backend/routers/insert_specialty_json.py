# backend/routers/insert_specialty_json.py
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Path as FPath, Query, HTTPException
from sqlmodel import Session, select

from backend.database import get_db
from backend.models import Track, Artist, Specialty, SpecialtyRanking
from backend.utils.json_helpers import load_full_json_file
from backend.utils.naming import slug_underscore, normalize_language_code
from shared.filepaths import get_json_path  # same helper you use elsewhere

router = APIRouter(tags=["Insert: Specialty"])
logger = logging.getLogger("insert_specialty")

@router.post("/specialty/{decade}/{genre}")
def insert_json_to_specialty_db(
    decade: str = FPath(..., description="Decade folder name, e.g. 'before 1990s' or '1950s'"),
    genre: str = FPath(..., description="Genre folder name shown on disk"),
    language: str = Query("english", description="Language name or code (e.g. english/español/es)"),
    filename: Optional[str] = Query(
        None,
        description="Optional explicit JSON filename. If omitted, it's constructed from decade/genre/language."
    ),
    preserve_intro: bool = Query(True, description="Keep existing intro text if present"),
    preserve_detail: bool = Query(True, description="Keep existing detail text if present"),
    preserve_artist_description: bool = Query(True, description="Keep existing artist descriptions if present"),
    force: bool = Query(False, description="If true, overwrite preserved fields"),
    db: Session = Depends(get_db),
):
    """
    Insert a JSON chart into the Specialty tables, using the same path/filename
    scheme as the main insert endpoint.
    """
    # ---- Resolve language & filename -----------------------------------------
    lang_code = normalize_language_code(language)  # e.g., "es" not "sp"
    decade_slug = slug_underscore(decade)         # e.g., "before_1990s"
    genre_slug = slug_underscore(genre)           # e.g., "latin_favorites"

    if filename:
        json_path = Path(filename)
    else:
        # Directory where JSONs live (your helper may return a dir or a file path)
        base = Path(get_json_path(decade, genre, lang_code))
        if base.suffix:  # if helper returned a file path, use its parent dir
            base = base.parent
        constructed = f"{decade_slug}_{genre_slug}_{lang_code}.json"
        json_path = base / constructed

    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"JSON file not found: {json_path}")

    logger.info(f"📁 Inserting Specialty JSON from: {json_path}")

    # ---- Load JSON & normalize shape -----------------------------------------
    data = load_full_json_file(str(json_path))

    # Support either "track" or "tracks" key (your generator uses "track")
    tracks = data.get("track") or data.get("tracks") or []
    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks found in JSON payload")

    # Derive specialty name/description from JSON (fallbacks to path params)
    specialty_name = data.get("genre") or genre
    decade_label = data.get("decade") or decade
    description = f"{specialty_name} - {decade_label}"

    # Language in file may be a verbose name; normalize it
    file_lang = normalize_language_code(data.get("language", lang_code))
    # Use the query param language as the source of truth if provided
    lang_final = file_lang or lang_code

    # ---- Ensure Specialty exists ---------------------------------------------
    spec_stmt = select(Specialty).where(
        Specialty.specialty_name == specialty_name,
        Specialty.language == lang_final,
    )
    specialty = db.exec(spec_stmt).first()
    if not specialty:
        specialty = Specialty(
            specialty_name=specialty_name,
            description=description,
            language=lang_final,
        )
        db.add(specialty)
        db.commit()
        db.refresh(specialty)
        logger.info(f"✅ Created specialty: {specialty_name} ({lang_final})")

    inserted = 0
    updated = 0

    for t in tracks:
        # Your generator uses "spotify_track_id". Keep compatibility with older "track_id".
        spotify_id = t.get("spotify_track_id") or t.get("track_id")
        if not spotify_id:
            logger.warning("⚠️ Skipping track with no spotify_track_id/track_id")
            continue

        artist_name = t.get("artist_name")
        track_name = t.get("track_name")
        if not artist_name or not track_name:
            logger.warning("⚠️ Skipping track missing artist_name/track_name")
            continue

        # ---- Ensure Artist ----------------------------------------------------
        artist_stmt = select(Artist).where(
            Artist.artist_name == artist_name,
            Artist.language == lang_final
        )
        artist = db.exec(artist_stmt).first()
        if not artist:
            artist_desc = t.get("artist_description", "")
            artist = Artist(
                artist_name=artist_name,
                artist_description=artist_desc,
                language=lang_final,
            )
            db.add(artist)
            db.commit()
            db.refresh(artist)
            logger.info(f"➕ Added artist: {artist_name} ({lang_final})")
        else:
            if not preserve_artist_description or force:
                # Update/overwrite description if provided
                new_desc = t.get("artist_description")
                if new_desc:
                    artist.artist_description = new_desc
                    db.add(artist)
                    db.commit()

        # ---- Ensure Track -----------------------------------------------------
        track_stmt = select(Track).where(Track.spotify_track_id == spotify_id)
        db_track = db.exec(track_stmt).first()
        if not db_track:
            db_track = Track(
                track_name=track_name,
                spotify_track_id=spotify_id,
                artist_id=artist.id,
                album_name=t.get("album_name", ""),
                duration_ms=t.get("duration_ms"),
                detail=t.get("detail", ""),
                language=lang_final,
            )
            db.add(db_track)
            db.commit()
            db.refresh(db_track)
            logger.info(f"🎵 Added track: {track_name} ({lang_final})")
        else:
            # Optionally update track detail if not preserving
            if (not preserve_detail or force) and t.get("detail"):
                db_track.detail = t["detail"]
                db.add(db_track)
                db.commit()

        # ---- Specialty Ranking (upsert-ish) ----------------------------------
        rank_num = t.get("rank")
        intro = t.get("intro", "")
        detail = t.get("detail", "")

        # Is there already a ranking row for this specialty+track?
        sr_stmt = select(SpecialtyRanking).where(
            SpecialtyRanking.specialty_id == specialty.id,
            SpecialtyRanking.track_id == spotify_id,  # NOTE: if your FK expects Track.id, adjust here
            SpecialtyRanking.language == lang_final,
        )
        sr = db.exec(sr_stmt).first()

        if sr:
            # Respect preserve flags unless forcing
            changed = False
            if rank_num is not None and sr.ranking != rank_num:
                sr.ranking = rank_num
                changed = True
            if (not preserve_intro or force) and intro:
                sr.intro = intro
                changed = True
            if (not preserve_detail or force) and detail:
                sr.detail = detail
                changed = True
            if changed:
                db.add(sr)
                updated += 1
        else:
            sr = SpecialtyRanking(
                specialty_id=specialty.id,
                track_id=spotify_id,   # <-- If this should be Track.id, use db_track.id instead
                ranking=rank_num,
                intro=intro,
                detail=detail,
                artist_id=artist.id,
                language=lang_final,
            )
            db.add(sr)
            inserted += 1

    db.commit()
    logger.info(f"✅ SpecialtyRanking rows — inserted: {inserted}, updated: {updated}")

    return {
        "message": "✅ Specialty JSON processed.",
        "specialty": specialty_name,
        "language": lang_final,
        "file": str(json_path),
        "inserted": inserted,
        "updated": updated,
    }
