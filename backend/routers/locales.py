# backend/routers/locales.py

from fastapi import APIRouter, Query, Depends, HTTPException
from typing import List, Dict
from sqlmodel import Session, select

from backend.database import get_db  # adjust if your path differs

from backend.models.dbmodels import (
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
        # ⬇️ your existing code starts here
        # 1) fetch ranks + track + artist by filtering TrackRanking directly
        decade_col = getattr(TrackRanking, "decade", None) or getattr(TrackRanking, "decade_name", None)
        genre_col  = getattr(TrackRanking, "genre",  None) or getattr(TrackRanking, "genre_name",  None)

        if decade_col is None or genre_col is None:
            raise HTTPException(
                status_code=500,
                detail="TrackRanking is missing decade/genre columns (expected 'decade' or 'decade_name', and 'genre' or 'genre_name')."
            )

        rows = db.exec(
            select(TrackRanking, Track, Artist)
            .where(decade_col == decade, genre_col == genre)
            .join(Track, Track.id == TrackRanking.track_id)
            .join(Artist, Artist.id == Track.artist_id)
            .order_by(TrackRanking.ranking)
            .limit(limit)
        ).all()

        if not rows:
            raise HTTPException(404, f"No rows found in track_ranking for decade='{decade}' and genre='{genre}'.")

        processed = 0
        for tr, tk, ar in rows:
            key = key_for(decade, genre, tr.ranking)
            payload = {
                "rank": tr.ranking,
                "decade": decade,
                "genre": genre,
                "trackName": tk.title,
                "artistName": ar.name,
                "yearReleased": getattr(tk, "year_released", None),
            }

            out = generate_es_pt_json(payload, languages)

            for lang in languages:
                data: Dict[str, str] = out.get(lang, {}) or {}
                intro = data.get("intro")
                detail = data.get("detail")
                artist_desc = data.get("artist_description")

                if intro and not db.exec(
                    select(TrackRankingLocale.id).where(
                        TrackRankingLocale.track_ranking_id == tr.id,
                        TrackRankingLocale.language_code == lang,
                    )
                ).first():
                    db.add(TrackRankingLocale(track_ranking_id=tr.id, language_code=lang, intro_text=intro))

                if detail and not db.exec(
                    select(TrackLocale.id).where(
                        TrackLocale.track_id == tk.id,
                        TrackLocale.language_code == lang,
                    )
                ).first():
                    db.add(TrackLocale(track_id=tk.id, language_code=lang, detail_text=detail))

                if artist_desc and not db.exec(
                    select(ArtistLocale.id).where(
                        ArtistLocale.artist_id == ar.id,
                        ArtistLocale.language_code == lang,
                    )
                ).first():
                    db.add(ArtistLocale(artist_id=ar.id, language_code=lang, artist_description_text=artist_desc))

            if not dry_run:
                db.commit()

            if not dry_run:
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

            processed += 1

        return {
            "decade": decade,
            "genre": genre,
            "languages": languages,
            "processed": processed,
            "dry_run": dry_run,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("backfill_locales failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
