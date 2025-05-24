from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, UniqueConstraint



# === core_tables schema ===
class Artist(SQLModel, table=True):
    __tablename__ = "artist"
    __table_args__ = (
        UniqueConstraint("spotify_artist_id", name="uq_spotify_artist_id"),
        {"schema": "core_tables", "extend_existing": True},
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    artist_name: str  # cleaned name already
    spotify_artist_id: Optional[str] = None
    artist_artwork: Optional[str] = None
    artist_description: Optional[str] = None



class Decade(SQLModel, table=True):
    __tablename__ = "decade"
    __table_args__ = {"schema": "core_tables", "extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    decade_name: str


class Genre(SQLModel, table=True):
    __tablename__ = "genre"
    __table_args__ = {"schema": "core_tables", "extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    genre_name: str


class Language(SQLModel, table=True):
    __tablename__ = "language"
    __table_args__ = {"schema": "core_tables", "extend_existing": True}

    code: str = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)


class Specialty(SQLModel, table=True):
    __tablename__ = "specialty"
    __table_args__ = {"schema": "core_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    specialty_name: str = Field(nullable=False)


# === join_tables schema ===
class ArtistGenre(SQLModel, table=True):
    __tablename__ = "artist_genre"
    __table_args__ = {"schema": "join_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    artist_id: Optional[int] = Field(default=None, foreign_key="core_tables.artist.id")
    genre_id: int = Field(foreign_key="core_tables.genre.id")


class DecadeGenre(SQLModel, table=True):
    __tablename__ = "decade_genre"
    __table_args__ = {"schema": "join_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    decade_id: Optional[int] = Field(default=None, foreign_key="core_tables.decade.id")
    genre_id: Optional[int] = Field(default=None, foreign_key="core_tables.genre.id")


class TrackGenre(SQLModel, table=True):
    __tablename__ = "track_genre"
    __table_args__ = {"schema": "join_tables", "extend_existing": True}

    track_id: int = Field(primary_key=True, foreign_key="track_tables.track.id")
    genre_id: int = Field(foreign_key="core_tables.genre.id")


# === ranking_tables schema ===
class SpecialtyRanking(SQLModel, table=True):
    __tablename__ = "specialty_ranking"
    __table_args__ = {"schema": "ranking_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    track_id: Optional[int] = Field(default=None, foreign_key="track_tables.track.id")
    specialty_id: Optional[int] = Field(default=None, foreign_key="core_tables.specialty.id")
    tracklist_id: int = Field(default=1, foreign_key="track_tables.tracklist.id")
    ranking: Optional[int] = Field(default=None)
    intro: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    intro_mp3_url: Optional[str] = Field(default=None)
    artist_id: Optional[int] = Field(default=None, foreign_key="core_tables.artist.id")
    ranking_date: Optional[datetime] = Field(default=None)


class Top40GenreRanking(SQLModel, table=True):
    __tablename__ = "top40_genre_ranking"
    __table_args__ = {"schema": "ranking_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    genre_id: int = Field(foreign_key="core_tables.genre.id")
    artist_id: int = Field(foreign_key="core_tables.artist.id")
    track_id: int = Field(foreign_key="track_tables.track.id")
    ranking: int = Field(nullable=False)
    info: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    ranking_date: Optional[datetime] = Field(default=None)
    intro_mp3_url: Optional[str] = Field(default=None)


class TrackRanking(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("track_id", "decade_genre_id", "tracklist_id", name="track_ranking_track_id_decade_genre_id_tracklist_id_key"),
        UniqueConstraint("ranking", "decade_genre_id", name="uix_rank_per_decade_genre"),
        {"schema": "ranking_tables", "extend_existing": True}
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    track_id: int = Field(foreign_key="track_tables.track.id")
    decade_genre_id: int = Field(foreign_key="join_tables.decade_genre.id")
    tracklist_id: int
    ranking: int
    intro: Optional[str] = None
    intro_mp3_url: Optional[str] = None
    ranking_date: Optional[str] = None


# === track_tables schema ===
class Tracklist(SQLModel, table=True):
    __tablename__ = "track_list"
    __table_args__ = {"schema": "track_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    curator: Optional[str] = Field(default=None)
    is_official: Optional[bool] = Field(default=False)
    language: Optional[str] = Field(default="English")
    notes: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)


class Track(SQLModel, table=True):
    __tablename__ = "track"
    __table_args__ = {"schema": "track_tables", "extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    track_name: str = Field(nullable=False)
    track_display_name: str = Field(nullable=False)
    spotify_track_id: str = Field(nullable=False)
    duration_ms: Optional[int] = Field(default=None)
    popularity: Optional[int] = Field(default=None)
    album_artwork: Optional[str] = Field(default=None)
    year_released: Optional[int] = Field(default=None)
    artist_id: int = Field(foreign_key="core_tables.artist.id")
    is_explicit: Optional[bool] = Field(default=False)
    created_at: Optional[datetime] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    detail_mp3_url: Optional[str] = Field(default=None)
