# backend/routers/ads_scripts.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
import logging

from backend.database import get_db
from backend.models.dbmodels import (
    Track, Artist, TrackRanking, DecadeGenre, Decade, Genre,
    TrackRankingLocale,  # if you use locales; safe to try/except
)
from backend.services.ads.script_generator import TrackAdInputs, generate_ad_script

logger = logging.getLogger("ads_scripts")
router = APIRouter(prefix="/ads", tags=["Ads / Scripts"])

def _fallback_locale_text(locale_row, default_text: str | None) -> str | None:
    """Return locale text if present, else default."""
    if locale_row and getattr(locale_row, "intro", None):
        return locale_row.intro
    return default_text

def _fallback_locale_detail(locale_row, default_text: str | None) -> str | None:
    if locale_row and getattr(locale_row, "detail", None):
        return locale_row.detail
    return default_text

@router.get("/script-by-track/{track_id}", summary="Generate a 30s ad script from one track")
def script_by_track(
    track_id: int,
    language: str = Query("en", description="Locale code for intro/detail if available"),
    db: Session = Depends(get_db),
):
    # Join Track -> Artist; try to find ranking/context to get rank/decade/genre
    stmt = (
        select(Track, Artist, TrackRanking, DecadeGenre, Decade, Genre)
        .join(Artist, Artist.id == Track.artist_id)
        .join(TrackRanking, TrackRanking.track_id == Track.id, isouter=True)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id, isouter=True)
        .join(Decade, Decade.id == DecadeGenre.decade_id, isouter=True)
        .join(Genre, Genre.id == DecadeGenre.genre_id, isouter=True)
        .where(Track.id == track_id)
        .limit(1)
    )
    row = db.exec(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Track {track_id} not found")

    track, artist, ranking, dg, decade, genre = row

    # Try locale row for intro/detail if you store them there
    locale_row = None
    try:
        if ranking:
            locale_row = db.exec(
                select(TrackRankingLocale).where(
                    (TrackRankingLocale.track_ranking_id == ranking.id) &
                    (TrackRankingLocale.language == language)
                )
            ).first()
    except Exception:
        locale_row = None

    intro_text = _fallback_locale_text(locale_row, getattr(ranking, "intro", None))
    detail_text = _fallback_locale_detail(locale_row, getattr(ranking, "detail", None))

    inputs = TrackAdInputs(
        track_title=track.title,
        artist_name=artist.name if artist else "Unknown Artist",
        year_released=str(track.release_year) if getattr(track, "release_year", None) else None,
        category=getattr(decade, "name", None),  # e.g., "1960s"
        genre=getattr(genre, "name", None),
        intro_text=intro_text,
        detail_text=detail_text,
        rank=getattr(ranking, "rank", None),
        language=language,
    )
    payload = generate_ad_script(inputs)
    logger.info("Generated ad script for track_id=%s (~%ss)", track_id, payload["estimated_seconds"])
    return payload

@router.get("/script-by-rank", summary="Generate a 30s ad script by (decade_id, genre_id, rank)")
def script_by_rank(
    decade_id: int = Query(...),
    genre_id: int = Query(...),
    rank: int = Query(..., ge=1, le=999),
    language: str = Query("en"),
    db: Session = Depends(get_db),
):
    # Find the TrackRanking row, then same joins
    tr_stmt = (
        select(TrackRanking)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .where((DecadeGenre.decade_id == decade_id) & (DecadeGenre.genre_id == genre_id) & (TrackRanking.rank == rank))
        .limit(1)
    )
    tr = db.exec(tr_stmt).first()
    if not tr:
        raise HTTPException(status_code=404, detail="No ranking found for that decade/genre/rank")

    stmt = (
        select(Track, Artist, TrackRanking, DecadeGenre, Decade, Genre)
        .join(Artist, Artist.id == Track.artist_id)
        .join(TrackRanking, TrackRanking.track_id == Track.id)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .join(Decade, Decade.id == DecadeGenre.decade_id)
        .join(Genre, Genre.id == DecadeGenre.genre_id)
        .where(TrackRanking.id == tr.id)
        .limit(1)
    )
    row = db.exec(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Unable to load joined rows for ranking")

    track, artist, ranking, dg, decade, genre = row

    # Locale (optional)
    locale_row = None
    try:
        locale_row = db.exec(
            select(TrackRankingLocale).where(
                (TrackRankingLocale.track_ranking_id == ranking.id) &
                (TrackRankingLocale.language == language)
            )
        ).first()
    except Exception:
        locale_row = None

    intro_text = _fallback_locale_text(locale_row, getattr(ranking, "intro", None))
    detail_text = _fallback_locale_detail(locale_row, getattr(ranking, "detail", None))

    inputs = TrackAdInputs(
        track_title=track.title,
        artist_name=artist.name if artist else "Unknown Artist",
        year_released=str(track.release_year) if getattr(track, "release_year", None) else None,
        category=getattr(decade, "name", None),
        genre=getattr(genre, "name", None),
        intro_text=intro_text,
        detail_text=detail_text,
        rank=getattr(ranking, "rank", None),
        language=language,
    )
    payload = generate_ad_script(inputs)
    logger.info(
        "Generated ad script for decade_id=%s genre_id=%s rank=%s (~%ss)",
        decade_id, genre_id, rank, payload["estimated_seconds"]
    )
    return payload
