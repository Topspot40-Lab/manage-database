from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

# === core_tables schema ===

class Artist(SQLModel, table=True):
    __tablename__ = "artist"
    __table_args__ = {"schema": "core_tables"}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    spotify_artist_id: str = Field(nullable=False)
    artist_artwork: Optional[str] = Field(default=None)
    artist_description: Optional[str] = Field(default=None)

class Decade(SQLModel, table=True):
    __tablename__ = "decade"
    __table_args__ = {"schema": "core_tables"}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)

class Genre(SQLModel, table=True):
    __tablename__ = "genre"
    __table_args__ = {"schema": "core_tables"}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    display_name: Optional[str] = Field(default=None)

class Language(SQLModel, table=True):
    __tablename__ = "language"
    __table_args__ = {"schema": "core_tables"}

    code: str = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)

class Specialty(SQLModel, table=True):
    __tablename__ = "specialty"
    __table_args__ = {"schema": "core_tables"}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)

# === join_tables schema ===

class ArtistGenre(SQLModel, table=True):
    __tablename__ = "artistgenre"
    __table_args__ = {"schema": "join_tables"}

    id: int = Field(default=None, primary_key=True)
    artistid: Optional[int] = Field(default=None, foreign_key="core_tables.artist.id")
    genreid: int = Field(foreign_key="core_tables.genre.id")

class DecadeGenre(SQLModel, table=True):
    __tablename__ = "decadegenre"
    __table_args__ = {"schema": "join_tables"}

    id: int = Field(default=None, primary_key=True)
    decadeid: Optional[int] = Field(default=None, foreign_key="core_tables.decade.id")
    genreid: Optional[int] = Field(default=None, foreign_key="core_tables.genre.id")

class TrackGenre(SQLModel, table=True):
    __tablename__ = "trackgenre"
    __table_args__ = {"schema": "join_tables"}

    track_id: int = Field(primary_key=True, foreign_key="track_tables.track.id")
    genre_id: int = Field(foreign_key="core_tables.genre.id")

# === ranking_tables schema ===

class SpecialtyRanking(SQLModel, table=True):
    __tablename__ = "specialtyranking"
    __table_args__ = {"schema": "ranking_tables"}

    id: int = Field(default=None, primary_key=True)
    trackid: Optional[int] = Field(default=None, foreign_key="track_tables.track.id")
    specialtyid: Optional[int] = Field(default=None, foreign_key="core_tables.specialty.id")
    tracklistid: Optional[int] = Field(default=None, foreign_key="track_tables.tracklist.id")
    rank: Optional[int] = Field(default=None)
    intro: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    descriptionlanguage: Optional[str] = Field(default="English", foreign_key="core_tables.language.code")
    artistid: Optional[int] = Field(default=None, foreign_key="core_tables.artist.id")
    rankingdate: Optional[datetime] = Field(default=None)

class Top40GenreRanking(SQLModel, table=True):
    __tablename__ = "top40genreranking"
    __table_args__ = {"schema": "ranking_tables"}

    id: int = Field(default=None, primary_key=True)
    genreid: int = Field(foreign_key="core_tables.genre.id")
    artistid: int = Field(foreign_key="core_tables.artist.id")
    trackid: int = Field(foreign_key="track_tables.track.id")
    rank: int = Field(nullable=False)
    info: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    rankingdate: Optional[datetime] = Field(default=None)

class TrackRanking(SQLModel, table=True):
    __tablename__ = "trackranking"
    __table_args__ = {"schema": "ranking_tables"}

    id: int = Field(default=None, primary_key=True)
    trackid: int = Field(foreign_key="track_tables.track.id")
    decadegenreid: int = Field(foreign_key="join_tables.decadegenre.id")
    tracklistid: int = Field(default=1)
    rank: int = Field(nullable=False)
    intro: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    descriptionlanguage: str = Field(default="english", foreign_key="core_tables.language.code")
    rankingdate: Optional[datetime] = Field(default=None)

# === track_tables schema ===

class TrackList(SQLModel, table=True):
    __tablename__ = "tracklist"
    __table_args__ = {"schema": "track_tables"}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    curator: Optional[str] = Field(default=None)
    isofficial: Optional[bool] = Field(default=False)
    language: Optional[str] = Field(default="English")
    notes: Optional[str] = Field(default=None)
    createdat: Optional[datetime] = Field(default=None)

class Track(SQLModel, table=True):
    __tablename__ = "track"
    __table_args__ = {"schema": "track_tables"}

    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    spotify_track_id: str = Field(nullable=False)
    duration_ms: Optional[int] = Field(default=None)
    popularity: Optional[int] = Field(default=None)
    album_artwork: Optional[str] = Field(default=None)
    year_released: Optional[int] = Field(default=None)
    artistid: int = Field(foreign_key="core_tables.artist.id")
    is_explicit: Optional[bool] = Field(default=False)
    createdat: Optional[datetime] = Field(default=None)
