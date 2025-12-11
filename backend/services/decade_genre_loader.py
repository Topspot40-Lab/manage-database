from sqlmodel import select

from backend.database import get_db_session
from backend.models.dbmodels import (
    Track,
    Artist,
    TrackRanking,
    DecadeGenre,
    Decade,
    Genre,
)


def load_decade_genre_rows(
    *,
    decade: str,
    genre: str,
    start_rank: int,
    end_rank: int,
):
    """
    Query all tracks for (decade, genre) in [start_rank, end_rank].
    Returns a list of tuples:
      (Track, Artist, TrackRanking, Decade, Genre)
    """
    with get_db_session() as db:
        q = (
            select(Track, Artist, TrackRanking, Decade, Genre)
            .join(Artist, Artist.id == Track.artist_id)
            .join(TrackRanking, TrackRanking.track_id == Track.id)
            .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
            .join(Decade, Decade.id == DecadeGenre.decade_id)
            .join(Genre, Genre.id == DecadeGenre.genre_id)
            .where(
                Decade.slug == decade,
                Genre.slug == genre,
                TrackRanking.ranking >= start_rank,
                TrackRanking.ranking <= end_rank,
            )
        )
        return db.exec(q).all()
