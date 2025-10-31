# backend/services/collection_import/collection_upsert.py
from sqlmodel import Session, select
from backend.models.collection_models import Collection


def upsert_collection(db: Session, slug: str, name: str, intro: str | None) -> Collection:
    """Ensure a collection exists and is up to date."""
    coll = db.exec(select(Collection).where(Collection.slug == slug)).first()
    if not coll:
        coll = Collection(name=name, slug=slug, intro=intro)
        db.add(coll)
        db.commit()
        db.refresh(coll)
        return coll

    dirty = False
    if coll.name != name:
        coll.name = name
        dirty = True
    if intro is not None and getattr(coll, "intro", None) != intro:
        coll.intro = intro
        dirty = True
    if dirty:
        db.add(coll)
        db.commit()
        db.refresh(coll)
    return coll
