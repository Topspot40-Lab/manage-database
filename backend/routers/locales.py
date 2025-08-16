# backend/routers/locales.py

from fastapi import APIRouter, Query, Depends, HTTPException
from typing import List, Dict
from sqlmodel import Session, select

from backend.database import get_db

from backend.models.dbmodels import (
    Decade, Genre, DecadeGenre,        # ⬅️ added
    TrackRanking, Track, Artist,
    TrackRankingLocale, TrackLocale, ArtistLocale,
)

from backend.utils.storage_keys import bucket_for, key_for
from backend.services.xai_localizer import generate_es_pt_json
from backend.services.elevenlabs_tts import synth_to_mp3_bytes
from backend.services.supabase_storage import upload_bytes
from backend.config import ELEVENLABS_API_KEY

import logging
log = logging.getLogger("locales")

router = APIRouter(prefix="/locales", tags=["Locales"])


def _get_decade_genre_id(db: Session, decade_name: str, genre_name: str) -> int:
    """Resolve (decade, genre) → decade_genre.id or raise 404s."""
    decade = db.exec(select(Decade).where(Decade.decade_name == decade_name)).first()
    if not decade:
        raise HTTPException(status_code=404, detail=f"Decade '{decade_name}' not found.")

    genre = db.exec(select(Genre).where(Genre.genre_name == genre_name)).first()
    if not genre:
        raise HTTPException(status_code=404, detail=f"Genre '{genre_name}' not found.")

    dg = db.exec(
        select(DecadeGenre).where(
            DecadeGenre.decade_id == decade.id,
            DecadeGenre.genre_id == genre.id
        )
    ).first()
    if not dg:
        raise HTTPException(
            status_code=404,
            detail=f"Decade/Genre combo not found for {decade_name}/{genre_name}."
        )
    return dg.id


@router.post("/backfill-decade-genre")
def backfill_locales(
    decade: str = Query(..., description="e.g., 1960s"),
    genre: str = Query(..., description="e.g., country"),
    languages: List[str] = Query(["es", "pt-BR"]),
    limit: int = Query(1, ge=1, le=500),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    try:
        # 1) Resolve decade_genre_id from normalized schema
        dg_id = _get_decade_genre_id(db, decade, genre)

        # 2) Fetch source rankings + track + artist via the combo id
        rows = db.exec(
            select(TrackRanking, Track, Artist)
            .where(TrackRanking.decade_genre_id == dg_id)
            .join(Track, Track.id == TrackRanking.track_id)
            .join(Artist, Artist.id == Track.artist_id)
            .order_by(TrackRanking.ranking)
            .limit(limit)
        ).all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No rankings found for {decade}/{genre}."
            )

        # 3) Build (and optionally persist) locales
        processed = 0
        planned_actions = []  # helpful preview in dry_run

        # Commit once at the end (if not dry_run)
        def _commit_once():
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

        for tr, tk, ar in rows:
            # Be resilient to field naming differences
            track_name = getattr(tk, "track_name", None)
            artist_name = getattr(ar, "artist_name", None)
            year_released = (
                getattr(tk, "year_released", None)
                or getattr(tk, "release_year", None)
            )

            if not track_name or not artist_name:
                log.warning(
                    "Missing track/artist names for ranking_id=%s (track_id=%s, artist_id=%s)",
                    tr.id, tk.id, ar.id
                )

            key = key_for(decade, genre, tr.ranking)
            payload = {
                "rank": tr.ranking,
                "decade": decade,
                "genre": genre,
                "trackName": track_name,
                "artistName": artist_name,
                "yearReleased": year_released,
            }

            out = generate_es_pt_json(payload, languages)

            # Prepare DB mutations
            for lang in languages:
                data: Dict[str, str] = out.get(lang, {}) or {}
                intro = data.get("intro")
                detail = data.get("detail")
                artist_desc = data.get("artist_description")

                planned_actions.append({
                    "ranking_id": tr.id,
                    "track_id": tk.id,
                    "artist_id": ar.id,
                    "language": lang,
                    "will_write": {
                        "intro": bool(intro),
                        "detail": bool(detail),
                        "artist_description": bool(artist_desc),
                    },
                    "storage_key": key,
                })

                # Skip DB writes if dry_run
                if dry_run:
                    continue

                # Intro (TrackRankingLocale)
                if intro and not db.exec(
                    select(TrackRankingLocale.id).where(
                        TrackRankingLocale.track_ranking_id == tr.id,
                        TrackRankingLocale.language_code == lang,
                    )
                ).first():
                    db.add(TrackRankingLocale(
                        track_ranking_id=tr.id,
                        language_code=lang,
                        intro_text=intro
                    ))

                # Detail (TrackLocale)
                if detail and not db.exec(
                    select(TrackLocale.id).where(
                        TrackLocale.track_id == tk.id,
                        TrackLocale.language_code == lang,
                    )
                ).first():
                    db.add(TrackLocale(
                        track_id=tk.id,
                        language_code=lang,
                        detail_text=detail
                    ))

                # Artist description (ArtistLocale)
                if artist_desc and not db.exec(
                    select(ArtistLocale.id).where(
                        ArtistLocale.artist_id == ar.id,
                        ArtistLocale.language_code == lang,
                    )
                ).first():
                    db.add(ArtistLocale(
                        artist_id=ar.id,
                        language_code=lang,
                        artist_description_text=artist_desc
                    ))

            processed += 1

        if not dry_run:
            _commit_once()

            # 4) TTS + upload (after DB commit), only when not dry_run
            for tr, tk, ar in rows:
                key = key_for(decade, genre, tr.ranking)
                # Recompute localization to avoid retaining lots of text in memory
                track_name = getattr(tk, "track_name", None)
                artist_name = getattr(ar, "artist_name", None)
                year_released = (
                    getattr(tk, "year_released", None)
                    or getattr(tk, "release_year", None)
                )
                payload = {
                    "rank": tr.ranking,
                    "decade": decade,
                    "genre": genre,
                    "trackName": track_name,
                    "artistName": artist_name,
                    "yearReleased": year_released,
                }
                out = generate_es_pt_json(payload, languages)

                for lang in languages:
                    data: Dict[str, str] = out.get(lang, {}) or {}
                    intro = data.get("intro")
                    detail = data.get("detail")
                    artist_desc = data.get("artist_description")

                    if intro:
                        mp3 = synth_to_mp3_bytes(intro, lang, kind="intro", api_key=ELEVENLABS_API_KEY)
                        upload_bytes(bucket_for("intro", lang), key, mp3, "audio/mpeg")
                    if detail:
                        mp3 = synth_to_mp3_bytes(detail, lang, kind="detail", api_key=ELEVENLABS_API_KEY)
                        upload_bytes(bucket_for("detail", lang), key, mp3, "audio/mpeg")
                    if artist_desc:
                        mp3 = synth_to_mp3_bytes(artist_desc, lang, kind="artist", api_key=ELEVENLABS_API_KEY)
                        upload_bytes(bucket_for("artist", lang), key, mp3, "audio/mpeg")

        # 5) Response
        return {
            "decade": decade,
            "genre": genre,
            "decade_genre_id": dg_id,
            "languages": languages,
            "processed": processed,
            "dry_run": dry_run,
            "sample_planned_actions": planned_actions[: min(10, len(planned_actions))],  # preview
            "note": "(dry-run) no DB writes or uploads performed" if dry_run else "localized rows written; mp3s uploaded",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("backfill_locales failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
