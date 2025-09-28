from sqlmodel import Session, select
from backend.models.dbmodels import Collection, CollectionTrackRanking

def get_collection_by_slug(db: Session, slug: str) -> Collection | None:
    return db.exec(select(Collection).where(Collection.slug == slug)).first()

def get_collection_rows(db: Session, collection_id: int) -> list[CollectionTrackRanking]:
    return db.exec(select(CollectionTrackRanking).where(
        CollectionTrackRanking.collection_id == collection_id
    )).all()

def get_collection_row_by_rank(db: Session, collection_id: int, rank: int) -> CollectionTrackRanking | None:
    return db.exec(select(CollectionTrackRanking).where(
        CollectionTrackRanking.collection_id == collection_id,
        CollectionTrackRanking.ranking == rank
    )).first()
