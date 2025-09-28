from sqlmodel import Session, select
from backend.models.dbmodels import DecadeGenre, TrackRanking

def get_decade_genre(db: Session, decade: str, genre: str) -> DecadeGenre | None:
    return db.exec(select(DecadeGenre).where(
        DecadeGenre.decade == decade, DecadeGenre.genre == genre
    )).first()

def get_rank_by_rank(db: Session, dg_id: int, rank: int) -> TrackRanking | None:
    return db.exec(select(TrackRanking).where(
        TrackRanking.decade_genre_id == dg_id,
        TrackRanking.ranking == rank
    )).first()

def get_all_ranks(db: Session, dg_id: int) -> list[TrackRanking]:
    return db.exec(select(TrackRanking).where(TrackRanking.decade_genre_id == dg_id)).all()
