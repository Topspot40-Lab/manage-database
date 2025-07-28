from typing import Optional
from datetime import datetime, UTC
from sqlmodel import SQLModel, Field, UniqueConstraint
from backend.models.enums import ModeFlag
from sqlalchemy import Column, Enum as SqlEnum  # 👈 Needed for proper SQL enum mapping



class DecadeGenreTrivia(SQLModel, table=True):
    __tablename__ = "decade_genre_trivia"

    id: Optional[int] = Field(default=None, primary_key=True)
    decade_genre_id: int = Field(foreign_key="decade_genre.id")
    trivia: str
    trivia_mp3_url: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))



class Artist(SQLModel, table=True):
    __tablename__ = "artist"
    __table_args__ = {
        "extend_existing": True,
    }

    id: Optional[int] = Field(default=None, primary_key=True)
    artist_name: str
    spotify_artist_id: Optional[str] = Field(default=None, nullable=True)
    artist_artwork: Optional[str] = None
    artist_description: Optional[str] = None
    not_on_spotify: bool = Field(default=False)  # ✅ Add this line




class Decade(SQLModel, table=True):
    __tablename__ = "decade"

    id: Optional[int] = Field(default=None, primary_key=True)
    decade_name: str


class Genre(SQLModel, table=True):
    __tablename__ = "genre"

    id: Optional[int] = Field(default=None, primary_key=True)
    genre_name: str


class Language(SQLModel, table=True):
    __tablename__ = "language"

    code: str = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)


class Specialty(SQLModel, table=True):
    __tablename__ = "specialty"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    specialty_name: str = Field(nullable=False)


class ArtistGenre(SQLModel, table=True):
    __tablename__ = "artist_genre"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    artist_id: Optional[int] = Field(default=None, foreign_key="artist.id")
    genre_id: int = Field(foreign_key="genre.id")


class DecadeGenre(SQLModel, table=True):
    __tablename__ = "decade_genre"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    decade_id: Optional[int] = Field(default=None, foreign_key="decade.id")
    genre_id: Optional[int] = Field(default=None, foreign_key="genre.id")


class TrackGenre(SQLModel, table=True):
    __tablename__ = "track_genre"
    __table_args__ = {"extend_existing": True}

    track_id: int = Field(primary_key=True, foreign_key="track.id")
    genre_id: int = Field(foreign_key="genre.id")


# === schema ===
class SpecialtyRanking(SQLModel, table=True):
    __tablename__ = "specialty_ranking"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    track_id: Optional[int] = Field(default=None, foreign_key="track.id")
    specialty_id: Optional[int] = Field(default=None, foreign_key="specialty.id")
    tracklist_id: int = Field(default=1, foreign_key="tracklist.id")
    ranking: Optional[int] = Field(default=None)
    intro: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    intro_mp3_url: Optional[str] = Field(default=None)
    artist_id: Optional[int] = Field(default=None, foreign_key="artist.id")
    ranking_date: Optional[datetime] = Field(default=None)


class Top40GenreRanking(SQLModel, table=True):
    __tablename__ = "top40_genre_ranking"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="genre.id")
    artist_id: int = Field(foreign_key="artist.id")
    track_id: int = Field(foreign_key="track.id")
    ranking: int = Field(nullable=False)
    info: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    ranking_date: Optional[datetime] = Field(default=None)
    intro_mp3_url: Optional[str] = Field(default=None)


class TrackRanking(SQLModel, table=True):
    __tablename__ = "track_ranking"  # ✅ explicitly define the table name
    __table_args__ = (
        UniqueConstraint("track_id", "decade_genre_id", "tracklist_id", name="track_ranking_track_id_decade_genre_id_tracklist_id_key"),
        UniqueConstraint("ranking", "decade_genre_id", name="uix_rank_per_decade_genre"),
        {"extend_existing": True}
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    track_id: int = Field(foreign_key="track.id")
    decade_genre_id: int = Field(foreign_key="decade_genre.id")
    tracklist_id: int
    ranking: int
    intro: Optional[str] = None
    ranking_date: Optional[str] = None


class Tracklist(SQLModel, table=True):
    __tablename__ = "track_list"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    curator: Optional[str] = Field(default=None)
    is_official: Optional[bool] = Field(default=False)
    language: Optional[str] = Field(default="English")
    notes: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)

class Track(SQLModel, table=True):
    __tablename__ = "track"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    track_name: str = Field(nullable=False)
    album_name: Optional[str] = Field(default=None)  # ✅ New field
    artist_display_name: Optional[str] = Field(default=None)  # ✅ NEW: replaces `track_display_name`
    spotify_track_id: str = Field(nullable=False)
    mode_flag: ModeFlag = Field(
        sa_column=Column(SqlEnum(ModeFlag, name="modeflag", create_constraint=True)),
        default=ModeFlag.SOLO
    )

    duration_ms: Optional[int] = Field(default=None)
    popularity: Optional[int] = Field(default=None)
    album_artwork: Optional[str] = Field(default=None)
    year_released: Optional[int] = Field(default=None)
    artist_id: int = Field(foreign_key="artist.id")
    featured_artist_id: Optional[int] = Field(default=None, foreign_key="artist.id")
    is_explicit: Optional[bool] = Field(default=False)
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))
    detail: Optional[str] = Field(default=None)

