# backend/routers/insert_specialty_json.py
import logging
from typing import Dict, Tuple, Optional

import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import and_
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, SQLAlchemyError
from sqlmodel import Session, select
from contextlib import nullcontext

from backend.database import get_db
from backend.models import (
    Artist,
    Track,
    Specialty,
    SpecialtyRanking,
    Genre,
)
from backend.services.supabase_storage import delete_intro_mp3_files_for_combo
from backend.utils.json_helpers import load_full_json_file
from backend.utils.mode_utils import ModeFlag, parse_mode_flag
from backend.utils.naming import normalize_language_code

# helpers (now in utils/)
from backend.utils.specialty_utils import (
    resolve_labels,
    parse_featured_keys,
    should_update,
    ensure_artist_genre_link,
)

logger = logging.getLogger(__name__)
specialty_router = APIRouter(prefix="", tags=["specialty-insert"])
# export as `router` so main.py can `import router as specialty_insert_router`
router = specialty_router
__all__ = ["router", "specialty_router"]


@specialty_router.post("/insert-specialty-json/{category}/{specialty}")
async def insert_specialty_json(
    category: str = Path(..., description="Category/Decade-like label, e.g. 'before 1990s'"),
    specialty: str = Path(..., description="Specialty name, e.g. 'latin favorites'"),
    language: str = Query("english", description="Language (name or code) like 'english'/'espanol'/'es'"),
    preserve_intro: bool = Query(True),
    preserve_detail: bool = Query(True),
    preserve_artist_description: bool = Query(True),
    force: bool = Query(False),
    filename: Optional[str] = Query(None, description="Optional override of the JSON filename"),
    # Transaction controls
    atomic: bool = Query(True, description="Run in a single DB transaction (recommended)."),
    dry_run: bool = Query(False, description="Do everything except the final commit; rolls back at the end."),
    db: Session = Depends(get_db),
):
    """
    Insert a Specialty + Artists + Tracks + SpecialtyRanking from a JSON file.

    Behavior mirrors your /insert-json-to-db endpoint:
      - preserves existing text by default (intro/detail/artist_description)
      - force=True wipes existing rankings (and deletes intro MP3s) before reinsert
      - supports DUET/FEATURED via mode_flag + featured artist creation
      - dry_run=True: validates and rolls back; skips MP3 deletions
      - atomic=True: single transaction; uses SAVEPOINT via begin_nested()
    """
    logger.info(f"Connected to DB; schema: {sqlalchemy.inspect(db.bind).default_schema_name}")

    # Helper to commit-or-flush depending on atomic
    def _savepoint():
        if atomic:
            db.flush()
        else:
            db.commit()

    # ---------- Resolve language + filename ----------
    lang_code = normalize_language_code(language)
    json_filename = filename or f"{category}_{specialty}_{lang_code}.json"

    # ---------- Load JSON ----------
    try:
        data = load_full_json_file(category, json_filename)
        logger.info(f"Loaded JSON file: {json_filename}")
        # Normalize artist to list if a dict slipped in
        if isinstance(data.get("artist"), dict):
            logger.warning("⚠️ Patching artist field from dict to list")
            data["artist"] = [data["artist"]]
    except FileNotFoundError:
        logger.error("JSON file not found")
        raise HTTPException(status_code=404, detail="JSON file not found")
    except Exception as e:
        logger.error(f"Error reading JSON: {e}")
        raise HTTPException(status_code=500, detail=f"Read error: {e}")

    # ---------- Core labels (centralized) ----------
    json_genre, json_category = resolve_labels(data, category, specialty)

    # Optional: fetch Genre row once for ArtistGenre linking
    genre_row = db.exec(select(Genre).where(Genre.genre_name == json_genre)).first()

    # Predeclare counters so they're available for dry_run exits
    inserted = 0
    updated = 0

    # Choose a transaction context that won't explode if one is already open
    tx_ctx = db.begin_nested() if atomic else nullcontext()

    try:
        with tx_ctx:
            # ---------- Ensure Specialty ----------
            spec_stmt = select(Specialty).where(
                Specialty.specialty_name == json_genre,
                Specialty.language == lang_code,
            )
            specialty_obj = db.exec(spec_stmt).first()
            if not specialty_obj:
                specialty_obj = Specialty(
                    specialty_name=json_genre,
                    description=f"{json_genre} - {json_category}",
                    language=lang_code,
                )
                db.add(specialty_obj)
                _savepoint()
                db.refresh(specialty_obj)
                logger.info(f"➕ Created Specialty: {json_genre} ({lang_code})")

            # ---------- Safety: Prevent duplicate population unless force ----------
            existing_sr = db.exec(
                select(SpecialtyRanking).where(
                    SpecialtyRanking.specialty_id == specialty_obj.id,
                    SpecialtyRanking.language == lang_code,
                )
            ).first()

            if existing_sr:
                if not force:
                    logger.warning(f"🚨 ABORT: Specialty already populated: {json_category} / {json_genre} / {lang_code}")
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Specialty '{json_category}/{json_genre}' (lang={lang_code}) already has rankings. "
                            f"Use force=true to overwrite and reset intro MP3s."
                        ),
                    )
                else:
                    if dry_run:
                        logger.warning(
                            f"⚠️ Force requested, but dry_run=True — would delete MP3s for {json_category}/{json_genre} (skipped)."
                        )
                    else:
                        logger.warning(
                            f"⚠️ Force mode — deleting existing intro MP3s for {json_category}/{json_genre}"
                        )
                        await delete_intro_mp3_files_for_combo(json_category, json_genre)
                        logger.info(f"✅ Deleted leftover intro MP3s for {json_category}/{json_genre}")

                    # Wipe prior rankings for this specialty+language
                    prior = db.exec(
                        select(SpecialtyRanking).where(
                            SpecialtyRanking.specialty_id == specialty_obj.id,
                            SpecialtyRanking.language == lang_code,
                        )
                    ).all()
                    for row in prior:
                        db.delete(row)
                    _savepoint()
                    logger.info("🧹 Cleared old SpecialtyRanking rows for this specialty/language.")

            # ---------- Build Artist map from JSON 'artist' ----------
            artist_map: Dict[str, int] = {}
            for a in data.get("artist", []):
                sid = a.get("spotify_artist_id")
                name = a["artist_name"].strip()

                # lookup by (spotify_id OR name) + language
                stmt = select(Artist)
                if sid:
                    stmt = stmt.where(Artist.spotify_artist_id == sid)
                else:
                    stmt = stmt.where(Artist.artist_name == name)
                stmt = stmt.where(Artist.language == lang_code)  # 👈 language-scoped lookup

                existing_artist = db.exec(stmt).first()

                if existing_artist:
                    artist_id = existing_artist.id
                    desc = a.get("artist_description")
                    if should_update(existing_artist.artist_description, preserve_artist_description):
                        existing_artist.artist_description = desc
                        logger.info(f"📝 Updated artist_description for: {name}")
                else:
                    artist = Artist(
                        artist_name=name,
                        spotify_artist_id=sid,
                        artist_artwork=a.get("artist_artwork"),
                        artist_description=a.get("artist_description"),
                        not_on_spotify=a.get("not_on_spotify", False),
                        language=lang_code,  # 👈 set language on create
                    )
                    db.add(artist)
                    _savepoint()
                    db.refresh(artist)
                    artist_id = artist.id
                    logger.info(f"➕ Added artist: {name} ({lang_code})")

                artist_map[sid or name] = artist_id
                ensure_artist_genre_link(db, artist_id, genre_row)

            _savepoint()

            # ---------- PRE-PASS: ensure featured artists exist (create if missing) ----------
            for t in data.get("track", []):
                parsed_flag = parse_mode_flag(t.get("mode_flag"))
                if parsed_flag not in (ModeFlag.DUET, ModeFlag.FEATURED):
                    continue

                feat_sid, feat_name = parse_featured_keys(t)
                key = feat_sid or feat_name
                if not key or key in artist_map:
                    continue

                fa = None
                if feat_sid:
                    q = select(Artist).where(Artist.spotify_artist_id == feat_sid, Artist.language == lang_code)
                    fa = db.exec(q).first()
                if not fa and feat_name:
                    q = select(Artist).where(Artist.artist_name == feat_name, Artist.language == lang_code)
                    fa = db.exec(q).first()

                if not fa and feat_name:
                    fa = Artist(
                        artist_name=feat_name,
                        spotify_artist_id=feat_sid,
                        language=lang_code,  # 👈 set language on create
                    )
                    db.add(fa)
                    _savepoint()
                    db.refresh(fa)
                    logger.info(f"➕ Added featured artist: {feat_name} ({lang_code})")

                if fa:
                    artist_map[key] = fa.id
                    ensure_artist_genre_link(db, fa.id, genre_row)

            _savepoint()

            # ---------- Upsert Tracks ----------
            track_map: Dict[Tuple[str, int], int] = {}
            for t in data.get("track", []):
                sid = t.get("spotify_track_id")
                artist_sid = t.get("spotify_artist_id")
                artist_id = artist_map.get(artist_sid or t["artist_name"].strip())

                parsed_flag = parse_mode_flag(t.get("mode_flag"))

                with db.no_autoflush:
                    if sid:
                        tstmt = select(Track).where(Track.spotify_track_id == sid, Track.language == lang_code)  # 👈
                        track = db.exec(tstmt).first()
                    else:
                        tstmt = select(Track).where(
                            and_(Track.track_name == t["track_name"], Track.artist_id == artist_id),
                            Track.language == lang_code,  # 👈
                        )
                        track = db.exec(tstmt).first()

                feat_sid, feat_name = parse_featured_keys(t)
                featured_artist_id = None
                if parsed_flag in (ModeFlag.DUET, ModeFlag.FEATURED):
                    featured_artist_id = artist_map.get(feat_sid or feat_name)

                if track:
                    logger.info(f"🔁 Updating track: {t['track_name']}")
                    track.track_name = t["track_name"]
                    track.artist_display_name = t.get("artist_display_name")
                    track.artist_id = artist_id
                    track.featured_artist_id = featured_artist_id
                    track.duration_ms = t.get("duration_ms")
                    track.popularity = t.get("popularity")
                    track.album_artwork = t.get("album_artwork")
                    track.year_released = t.get("year_released")
                    track.is_explicit = t.get("is_explicit")
                    track.created_at = t.get("created_at")
                    track.album_name = t.get("album_name")
                    track.mode_flag = parsed_flag.value if parsed_flag else None

                    if hasattr(track, "mode_flag_detail"):
                        setattr(track, "mode_flag_detail", t.get("mode_flag_detail"))

                    if should_update(track.detail, preserve_detail):
                        track.detail = t.get("detail")
                        logger.info(f"📝 Updated detail for: {t['track_name']}")
                else:
                    logger.info(f"➕ Creating new track: {t['track_name']}")
                    track_kwargs = dict(
                        track_name=t["track_name"],
                        artist_display_name=t.get("artist_display_name"),
                        artist_id=artist_id,
                        featured_artist_id=featured_artist_id,
                        spotify_track_id=sid,
                        duration_ms=t.get("duration_ms"),
                        popularity=t.get("popularity"),
                        album_artwork=t.get("album_artwork"),
                        year_released=t.get("year_released"),
                        is_explicit=t.get("is_explicit"),
                        created_at=t.get("created_at"),
                        detail=t.get("detail"),
                        album_name=t.get("album_name"),
                        mode_flag=parsed_flag.value if parsed_flag else None,
                        language=lang_code,  # 👈 set language on create
                    )
                    if "mode_flag_detail" in t and hasattr(Track, "mode_flag_detail"):
                        track_kwargs["mode_flag_detail"] = t.get("mode_flag_detail")

                    track = Track(**track_kwargs)
                    db.add(track)
                    _savepoint()
                    db.refresh(track)

                track_map[(track.track_name, artist_id)] = track.id

            _savepoint()

            # ---------- Insert/Update SpecialtyRanking ----------
            for r in data.get("track_ranking", []):
                spotify_tid = r.get("track_id")
                if not spotify_tid:
                    logger.warning("🚫 Skipping ranking entry — no track_id")
                    continue

                track_obj = db.exec(select(Track).where(Track.spotify_track_id == spotify_tid)).first()
                if not track_obj:
                    logger.warning(f"🚫 Track not found in DB with Spotify ID: {spotify_tid}")
                    continue

                stmt_sr = select(SpecialtyRanking).where(
                    and_(
                        SpecialtyRanking.specialty_id == specialty_obj.id,
                        SpecialtyRanking.track_id == track_obj.id,
                        SpecialtyRanking.language == lang_code,
                    )
                )
                sr = db.exec(stmt_sr).first()

                if sr:
                    sr.ranking = r.get("rank")
                    intro = r.get("intro")
                    if should_update(sr.intro, preserve_intro):
                        sr.intro = intro
                        logger.info(f"📝 Updated intro for: {track_obj.track_name}")
                    updated += 1
                else:
                    db.add(
                        SpecialtyRanking(
                            specialty_id=specialty_obj.id,
                            track_id=track_obj.id,
                            ranking=r.get("rank"),
                            intro=r.get("intro"),
                            artist_id=track_obj.artist_id,
                            language=lang_code,
                        )
                    )
                    inserted += 1

            _savepoint()

            # ---------- Finalize inside the context ----------
            if dry_run:
                logger.info("🧪 DRY RUN: rolling back all changes.")
                # Raising a sentinel lets the context roll back cleanly
                raise RuntimeError("__DRY_RUN__")

        # Only reached if no exception and not dry_run
        if atomic:
            db.commit()

        logger.info(f"✅ Specialty import complete. Inserted rankings: {inserted}, updated: {updated}")
        return {
            "status": "success",
            "message": f"Inserted {json_filename}",
            "specialty": json_genre,
            "category": json_category,
            "language": lang_code,
            "inserted": inserted,
            "updated": updated,
        }

    # ---- Narrow exception handling ----
    except RuntimeError as e:
        # Catch the dry-run sentinel
        if str(e) == "__DRY_RUN__":
            return {
                "status": "dry_run",
                "message": f"Validated {json_filename} (no changes committed).",
                "specialty": json_genre,
                "category": json_category,
                "language": lang_code,
                "inserted_would_be": inserted,
                "updated_would_be": updated,
            }
        # not our sentinel: treat as generic error below
        db.rollback()
        logger.exception("RuntimeError during specialty insert")
        raise HTTPException(status_code=500, detail="Runtime error while inserting specialty JSON.")

    except HTTPException:
        db.rollback()
        raise

    except (IntegrityError, DataError, OperationalError) as e:
        db.rollback()
        logger.exception("Database error while inserting specialty JSON")
        raise HTTPException(status_code=500, detail="Database error while inserting specialty JSON.")

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("SQLAlchemy error while inserting specialty JSON")
        raise HTTPException(status_code=500, detail="Database error while inserting specialty JSON.")
