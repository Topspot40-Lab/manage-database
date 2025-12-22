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

    print("🧪 load_decade_genre_rows CALLED")
    print("   decade arg    :", decade)
    print("   genre arg     :", genre)
    print("   start_rank    :", start_rank)
    print("   end_rank      :", end_rank)

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

        rows = db.exec(q).all()

        print("🧪 load_decade_genre_rows RESULT")
        print("   rows returned :", len(rows))

        if rows:
            track, artist, tr_rank, dec, gen = rows[0]
            print("   SAMPLE ROW →")
            print("     track      :", track.track_name)
            print("     artist     :", artist.artist_name)
            print("     rank       :", tr_rank.ranking)
            print("     decade DB  :", dec.decade_name)
            print("     genre DB   :", gen.genre_name)
        else:
            print("   ⚠️ NO ROWS MATCHED QUERY")

        return rows
