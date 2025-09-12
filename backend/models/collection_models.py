# backend/models/collection_models.py
from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import UniqueConstraint, CheckConstraint

class CollectionType(str, Enum):
    DECADE_GENRE = "DECADE_GENRE"
    COLLECTION = "COLLECTION"

class Collection(SQLModel, table=True):
    __tablename__ = "collection"
    __table_args__ = (
        CheckConstraint("collection_type IN ('DECADE_GENRE','COLLECTION')", name="chk_collection_type"),
        UniqueConstraint("slug", name="uq_collection_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True)  # uniqueness enforced by uq_collection_slug
    collection_type: CollectionType

    # Optional FKs
    decade_id: Optional[int] = Field(default=None, foreign_key="decade.id")
    genre_id: Optional[int] = Field(default=None, foreign_key="genre.id")

    intro: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    rankings: List["CollectionTrackRanking"] = Relationship(
        back_populates="collection",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

class CollectionTrackRanking(SQLModel, table=True):
    __tablename__ = "collection_track_ranking"
    __table_args__ = (
        UniqueConstraint("collection_id", "track_id", name="uix_ctr_collection_track"),
        UniqueConstraint("collection_id", "ranking",  name="uix_ctr_collection_rank"),
        CheckConstraint("ranking >= 1", name="chk_ctr_ranking_positive"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    collection_id: int = Field(foreign_key="collection.id", index=True)
    track_id: int = Field(foreign_key="track.id", index=True)
    ranking: int = Field(index=True)

    # parity with TrackRanking
    info: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    collection: Optional["Collection"] = Relationship(back_populates="rankings")
    locales: List["CollectionTrackRankingLocale"] = Relationship(
        back_populates="ranking",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

class CollectionTrackRankingLocale(SQLModel, table=True):
    __tablename__ = "collection_track_ranking_locale"
    __table_args__ = (
        UniqueConstraint("collection_track_ranking_id", "lang", name="uq_ctr_locale"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    collection_track_ranking_id: int = Field(
        foreign_key="collection_track_ranking.id", index=True
    )

    # Mirrors DB columns
    lang: str
    intro_text: str
    tts_key: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    ranking: Optional["CollectionTrackRanking"] = Relationship(back_populates="locales")
