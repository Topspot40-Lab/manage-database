# backend/routers/supabase_loader/list_collections.py
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from backend.database import get_db
from backend.models.collection_models import Collection

router = APIRouter(tags=["Supabase: Collections"])

@router.get("/list-collections")
def list_collections(db: Session = Depends(get_db)):
    """
    Return all available collections with id, name, and slug.
    Used for dropdown menus on the TopSpot Options page.
    """
    rows = db.exec(
        select(Collection.id, Collection.name, Collection.slug).order_by(Collection.name)
    ).all()

    return [
        {"id": r.id, "name": r.name, "slug": r.slug}
        for r in rows
    ]
