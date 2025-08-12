from __future__ import annotations
from typing import Optional
from datetime import datetime, UTC

from sqlalchemy import UniqueConstraint, CheckConstraint, ForeignKey, Column, String
# from sqlalchemy.orm import Mapped
from sqlmodel import SQLModel, Field, Relationship  # <-- use Relationship from sqlmodel
# from sqlmodel import SQLModel, Field

"""
MODE EXPLANATION

1) Decade-Genre Mode:
   - Decade + Genre combo is defined in DecadeGenre.
   - TrackRanking rows point to a DecadeGenre via decade_genre_id.
   - For now, language for genres/tracks/artists is "en".

2) Category-Specialty Mode:
   - Category + Specialty combo is defined in SpecialtyCategory.
   - Specialty supports multiple languages (e.g., "es"), and associated tracks/artists
     should reflect that language in their rows.
   - SpecialtyRanking rows reference SpecialtyCategory.
"""

# ---- Decade/Genre mode ------------------------------------------------------


class Decade(SQLModel, table=True):
    __tablename__ = "decade"
    id: Optional[int] = Field(default=None, primary_key=True)
    decade_name: str = Field(index=True, unique=True, sa_type=String(32))

class Genre(SQLModel, table=True):
    __tablename__ = "genre"
    id: Optional[int] = Field(default=None, primary_key=True)
    genre_name: str = Field(index=True, unique=True, sa_type=String(48))

class DecadeGenre(SQLModel, table=True):
    __tablename__ = "decade_genre"
    __table_args__ = (UniqueConstraint("decade_id", "genre_id", name="uq_decade_genre"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    decade_id: int = Field(foreign_key="decade.id", index=True)
    genre_id: int = Field(foreign_key="genre.id", index=True)

class TrackRanking(SQLModel, table=True):
    __tablename__ = "track_ranking"
    id: Optional[int] = Field(default=None, primary_key=True)
    decade_genre_id: int = Field(foreign_key="decade_genre.id", index=True)
    track_id: int = Field(foreign_key="track.id", index=True)
    rank: int = Field(index=True)

# ---- Category/Specialty mode ------------------------------------------------


class Category(SQLModel, table=True):
    __tablename__ = "category"
    __table_args__ = (UniqueConstraint("category_name", name="uq_category_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    category_name: str = Field(nullable=False)

    specialty_categories: list["SpecialtyCategory"] = Relationship(
        back_populates="category",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

class Specialty(SQLModel, table=True):
    __tablename__ = "specialty"
    __table_args__ = (UniqueConstraint("specialty_name", "language", name="uq_specialty_lang"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    specialty_name: str = Field(nullable=False)
    language: str = Field(default="en", max_length=2)

    # one-to-many -> SpecialtyCategory
    specialty_categories: list["SpecialtyCategory"] = Relationship(
        back_populates="specialty",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SpecialtyCategory(SQLModel, table=True):
    __tablename__ = "specialty_category"
    __table_args__ = (UniqueConstraint("category_id", "specialty_id", name="uq_specialty_category"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id", nullable=False)
    specialty_id: int = Field(foreign_key="specialty.id", nullable=False)

    category: "Category" = Relationship(back_populates="specialty_categories")
    specialty: "Specialty" = Relationship(back_populates="specialty_categories")

    rankings: list["SpecialtyRanking"] = Relationship(
        back_populates="specialty_category",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SpecialtyRanking(SQLModel, table=True):
    __tablename__ = "specialty_ranking"
    __table_args__ = (
        UniqueConstraint("specialty_category_id", "ranking", name="uix_rank_per_specialtycat"),
        UniqueConstraint("specialty_category_id", "track_id", name="uix_track_once_per_specialtycat"),
        CheckConstraint("ranking > 0", name="ck_specialty_ranking_positive"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # keep explicit ondelete behaviors via sa_column
    specialty_category_id: int = Field(
        sa_column=Column(ForeignKey("specialty_category.id", ondelete="CASCADE"), nullable=False)
    )
    track_id: int = Field(
        sa_column=Column(ForeignKey("track.id", ondelete="RESTRICT"), nullable=False)
    )

    ranking: int = Field(nullable=False)
    language: str = Field(sa_column=Column(String(2), server_default="en"), default="en", max_length=2)
    intro: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    track: "Track" = Relationship(back_populates="specialty_rankings")
    specialty_category: "SpecialtyCategory" = Relationship(back_populates="rankings")



# ---- Core entities ----------------------------------------------------------


class Artist(SQLModel, table=True):
    __tablename__ = "artist"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, sa_type=String(128))

class Track(SQLModel, table=True):
    __tablename__ = "track"
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, sa_type=String(160))
    artist_id: int = Field(foreign_key="artist.id", index=True)

    specialty_rankings: list["SpecialtyRanking"] = Relationship(back_populates="track")


class Language(SQLModel, table=True):
    __tablename__ = "language"
    code: str = Field(primary_key=True, sa_type=String(2))  # was max_length=2
    name: str = Field(nullable=False)


class ArtistGenre(SQLModel, table=True):
    __tablename__ = "artist_genre"
    __table_args__ = (UniqueConstraint("artist_id", "genre_id", name="uq_artist_genre"),)

    id: int = Field(default=None, primary_key=True)
    artist_id: int = Field(foreign_key="artist.id")
    genre_id: int = Field(foreign_key="genre.id")


class TrackGenre(SQLModel, table=True):
    __tablename__ = "track_genre"

    track_id: int = Field(foreign_key="track.id", primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", primary_key=True)


# === schema / views ==========================================================


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
    created_at: Optional[datetime] = Field(default=None)
    intro_mp3_url: Optional[str] = Field(default=None)


class Tracklist(SQLModel, table=True):
    __tablename__ = "track_list"
    __table_args__ = (UniqueConstraint("name", "curator", "language", name="uq_tracklist_name_curator_lang"),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    curator: str | None = None
    is_official: bool | None = Field(default=False)
    language: str | None = Field(default="en", max_length=2)
    notes: str | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))


class DecadeGenreTrivia(SQLModel, table=True):
    __tablename__ = "decade_genre_trivia"

    id: Optional[int] = Field(default=None, primary_key=True)
    decade_genre_id: int = Field(foreign_key="decade_genre.id")
    trivia: str
    trivia_mp3_url: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))
