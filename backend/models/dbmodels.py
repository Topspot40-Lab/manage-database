
from __future__ import annotations
from typing import Optional
from sqlalchemy import UniqueConstraint, CheckConstraint, Index, ForeignKey
from sqlalchemy import Column, String
from datetime import datetime, UTC
from sqlmodel import SQLModel, Field, Relationship


'''

1) Decade-Genre Mode is where the user selects a decade and genre. 
The frontend queries the supabase for the the correct combination based 
on the DecadeGenre table and the language of the information is based on 
the the value of the language column. This will always be "en" for english for the present. 
All of the tracks and artists associated with this mode should have the language value of "en". 
The TrackRanking Table determines the ranking of the tracks for that combination. 
All of the "intro" text and mp3's will be in english for this mode.

2) Category-Specialty Mode will work in a similar way to the Decade-Genre Mode, 
except this mode will allow for different languages. In this mode, the "Category" table will work 
in a similar way as the "Decade" table in the Decade-Genre mode and the "Specialty" table will work 
in a similar way to the "genre" mode in the Decade-Genre mode. The SpecialtyCategory join Table works 
in a similar was as the DecadeGenre Table in the Decade-Genre Mode. HOWEVER:  The specialty language 
colum CAN have other languages, eg. spanish = "es". This means that any artists and tracks identified 
with a different language (eg "es") in the specialty table, should also have that language value in the 
associate artist and track table for that ranking set.

The Decade table defines the decades for the Decade-Genre Mode
eg. 1950s, 1960s, ...
The Genre table defines the genres for the Decade-Genre Mode
eg. "country", "pop", "rock" ..

The DecadeGenre table defines a join table for a particular combination of the decade 
and genre that will be used in the TrackRanking table

The TrackRanking table uses an id from the DecadeGenre Table to 
relate the rankings of track for that combination

The language of the track table and the artist table entries
is determined by the "genre" table. For now, all of the genre language
value should be limited to "en" for English

'''
# ---- Decade/Genre mode ------------------------------------------------------

class Decade(SQLModel, table=True):
    __tablename__ = "decade"
    id: Optional[int] = Field(default=None, primary_key=True)
    decade_name: str = Field(nullable=False)

class Genre(SQLModel, table=True):
    __tablename__ = "genre"
    id: Optional[int] = Field(default=None, primary_key=True)
    genre_name: str = Field(nullable=False)
    language: Optional[str] = Field(default="en", max_length=2)

class DecadeGenre(SQLModel, table=True):
    __tablename__ = "decade_genre"
    __table_args__ = (
        UniqueConstraint("decade_id", "genre_id", name="uq_decade_genre"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    decade_id: Optional[int] = Field(default=None, foreign_key="decade.id")
    genre_id: Optional[int] = Field(default=None, foreign_key="genre.id")

    decade: Optional["Decade"] = Relationship()
    genre: Optional["Genre"] = Relationship()

class TrackRanking(SQLModel, table=True):
    __tablename__ = "track_ranking"
    __table_args__ = (
        UniqueConstraint("decade_genre_id", "ranking", name="uix_rank_per_decade_genre"),
        UniqueConstraint("decade_genre_id", "track_id", name="uix_track_once_per_decade_genre"),
        CheckConstraint("ranking > 0", name="ck_track_ranking_positive"),
        Index("ix_tr_decade_genre_rank", "decade_genre_id", "ranking"),
    )

    id: int | None = Field(default=None, primary_key=True)

    # Optional: cascade deletes if you ever delete a DecadeGenre or Track
    decade_genre_id: int = Field(sa_column=Column(
        ForeignKey("decade_genre.id", ondelete="CASCADE")
    ))
    track_id: int = Field(sa_column=Column(
        ForeignKey("track.id", ondelete="RESTRICT")  # or "CASCADE" if you prefer
    ))

    ranking: int = Field(nullable=False)

    # If this is always 'en' in Decade/Genre mode, keep it for easy unions,
    # but give the DB a default and still assert in your endpoint.
    language: str = Field(
        sa_column=Column(String(2), server_default="en"),
        default="en",
        max_length=2
    )

    intro: str | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))

    # Optional relationships (handy in ORM code)
    track: Track | None = Relationship(back_populates="rankings")  # ✅
    decade_genre: DecadeGenre | None = Relationship()  # ✅


#####################################################


'''
The Category table defines the decades for the Specialty-Category Mode
eg. "before 1990s", "after 1990s" ...
The Specialty table defines the specialty names for the Specialty-Category Mode
eg. "latin favorites", "brazil favorites" ....

The SpecialtyCategory table defines a join table for a particular combination of the category 
and specialty that will be used in the SpecialtyRanking table

The SpecialtyRanking table uses an id from the CategorySpecialty Table to 
relate the rankings of track for that combination

The language of the track table and the artist table entries
is determined by the "specialty" table.
eg "latin favorites" will have a language value of "es" for espanol
When the language is "es", then the corresponding artist and track languages
in their table should also be set to language = "es"

'''
# ---- Category/Specialty mode ------------------------------------------------

class Specialty(SQLModel, table=True):
    __tablename__ = "specialty"
    __table_args__ = (
        UniqueConstraint("specialty_name", "language", name="uq_specialty_lang"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    specialty_name: str = Field(nullable=False)
    language: str = Field(default="en", max_length=2)

class Category(SQLModel, table=True):
    __tablename__ = "category"  # <- fix: not "specialty"
    __table_args__ = (
        UniqueConstraint("category_name", name="uq_category_name"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    category_name: str = Field(nullable=False)

class SpecialtyCategory(SQLModel, table=True):
    __tablename__ = "specialty_category"
    __table_args__ = (
        UniqueConstraint("category_id", "specialty_id", name="uq_specialty_category"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id")   # <- fix names + FKs
    specialty_id: int = Field(foreign_key="specialty.id")

    category: Optional["Category"] = Relationship()
    specialty: Optional["Specialty"] = Relationship()


class SpecialtyRanking(SQLModel, table=True):
    __tablename__ = "specialty_ranking"
    __table_args__ = (
        UniqueConstraint("specialty_id", "ranking", name="uix_rank_per_specialty"),
        UniqueConstraint("specialty_id", "track_id", name="uix_track_once_per_specialty"),
        CheckConstraint("ranking > 0", name="ck_specialty_ranking_positive"),
    )

    id: int | None = Field(default=None, primary_key=True)

    # If you ever delete a Specialty, its rankings should go too:
    specialty_id: int = Field(sa_column=Column(
        ForeignKey("specialty.id", ondelete="CASCADE")
    ))

    # Usually don't allow deleting a Track that’s referenced in a list:
    track_id: int = Field(sa_column=Column(
        ForeignKey("track.id", ondelete="RESTRICT")
    ))

    ranking: int = Field(nullable=False)

    # Mirror the container’s language; keep code-level assertion on insert
    language: str = Field(
        sa_column=Column(String(2), server_default="en"),
        default="en",
        max_length=2
    )

    intro: str | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))

    # Optional relationships
    track: Track | None = Relationship()  # ✅
    specialty: Specialty | None = Relationship()  # ✅


#####################################################
# ---- Core entities (minimal edits) ------------------------------------------

class Artist(SQLModel, table=True):
    __tablename__ = "artist"
    __table_args__ = (
        # same human name can exist in multiple languages, but unique inside one
        UniqueConstraint("artist_name", "language", name="uq_artist_name_lang"),
        # allow same Spotify ID in multiple languages (on purpose)
        UniqueConstraint("spotify_artist_id", "language", name="uq_artist_spotify_lang"),
    )
    id: int | None = Field(default=None, primary_key=True)
    artist_name: str = Field(nullable=False)
    spotify_artist_id: str | None = None
    artist_artwork: str | None = None
    artist_description: str | None = None
    not_on_spotify: bool = Field(default=False)
    language: str = Field(default="en", max_length=2)

class Track(SQLModel, table=True):
    __tablename__ = "track"
    __table_args__ = (
        UniqueConstraint("spotify_track_id", "language", name="uq_track_spotify_lang"),
        UniqueConstraint("artist_id", "track_name", "language",
                         name="uq_track_name_by_artist_lang"),
    )
    id: int | None = Field(default=None, primary_key=True)
    track_name: str = Field(nullable=False)
    spotify_track_id: str = Field(nullable=False)
    artist_id: int = Field(foreign_key="artist.id")
    featured_artist_id: int | None = Field(default=None, foreign_key="artist.id")
    duration_ms: int | None = None
    album_artwork: str | None = None
    year_released: int | None = None
    detail: str | None = None   # your TTS text source
    language: str = Field(default="en", max_length=2)


class Language(SQLModel, table=True):
    __tablename__ = "language"
    code: str = Field(primary_key=True, max_length=2)
    name: str = Field(nullable=False)

class ArtistGenre(SQLModel, table=True):
    __tablename__ = "artist_genre"
    __table_args__ = (
        UniqueConstraint("artist_id", "genre_id", name="uq_artist_genre"),
    )
    id: int = Field(default=None, primary_key=True)
    artist_id: int = Field(foreign_key="artist.id")
    genre_id: int = Field(foreign_key="genre.id")


class TrackGenre(SQLModel, table=True):
    __tablename__ = "track_genre"
    # __table_args__ = (UniqueConstraint("track_id","genre_id", name="uq_track_genre"),)  # remove this

    track_id: int = Field(foreign_key="track.id", primary_key=True)
    genre_id: int = Field(foreign_key="genre.id", primary_key=True)

# === schema ===

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
    __table_args__ = (
        UniqueConstraint("name", "curator", "language", name="uq_tracklist_name_curator_lang"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    curator: str | None = None          # e.g., username/email/org
    is_official: bool | None = Field(default=False)  # your own TopSpot-curated lists
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
