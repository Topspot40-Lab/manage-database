# backend/routers/catalog.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from backend.database import get_db
from backend.models.dbmodels import Decade, Genre
from backend.models.collection_models import Collection
import logging

router = APIRouter(prefix="/catalog", tags=["Catalog"])
logger = logging.getLogger(__name__)

@router.get("/summary")
def get_catalog_summary(db: Session = Depends(get_db)):
    """
    Returns simple lists of decades, genres, and collections
    for populating dropdown menus on the TopSpot40 Options Page.
    """
    try:
        decades = [d.decade_name for d in db.exec(select(Decade)).all()]
        genres = [g.genre_name for g in db.exec(select(Genre)).all()]
        collections = [c.name for c in db.exec(select(Collection)).all()]

        logger.info("📚 Catalog summary retrieved: %d decades, %d genres, %d collections",
                    len(decades), len(genres), len(collections))

        return {
            "decades": decades,
            "genres": genres,
            "collections": collections
        }

    except Exception as e:
        logger.exception("❌ Failed to load catalog summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
