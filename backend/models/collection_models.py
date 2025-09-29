from __future__ import annotations

from typing import Optional, TYPE_CHECKING   # ← add TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import UniqueConstraint, CheckConstraint, Column, ForeignKey
from sqlalchemy.orm import relationship as sa_relationship  # ✅ lowercase alias

if TYPE_CHECKING:
    from backend.models.dbmodels import Track  # type-only import


class Collection(SQLModel, table=True):
    __tablename__ = "collection"
    __table_args__ = (UniqueConstraint("slug", name="uq_collection_slug"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True)
    intro: Optional[str] = None

    # Force the target using sa_relationship=...
    rankings: list["CollectionTrackRanking"] = Relationship(
        sa_relationship=sa_relationship(
            "CollectionTrackRanking",
            back_populates="collection",
            cascade="all, delete-orphan",
        )
    )


class CollectionTrackRanking(SQLModel, table=True):
    __tablename__ = "collection_track_ranking"
    __table_args__ = (
        UniqueConstraint("collection_id", "track_id", name="uix_ctr_collection_track"),
        UniqueConstraint("collection_id", "ranking",  name="uix_ctr_collection_rank"),
        CheckConstraint("ranking > 0", name="ck_ctr_ranking_positive"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    collection_id: int = Field(
        sa_column=Column(
            ForeignKey("collection.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    track_id: int = Field(
        sa_column=Column(
            ForeignKey("track.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    ranking: int = Field(index=True)
    intro: Optional[str] = None

    collection: "Collection" = Relationship(
        sa_relationship=sa_relationship(
            "Collection",
            back_populates="rankings",
        )
    )
    locales: list["CollectionTrackRankingLocale"] = Relationship(
        sa_relationship=sa_relationship(
            "CollectionTrackRankingLocale",
            back_populates="ranking",
            cascade="all, delete-orphan",
        )
    )

    # NEW: relationship to Track so loader options can use .track
    track: "Track" = Relationship(
        sa_relationship=sa_relationship(
            "Track",
            back_populates="collection_rankings",
        )
    )



class CollectionTrackRankingLocale(SQLModel, table=True):
    __tablename__ = "collection_track_ranking_locale"
    __table_args__ = (
        UniqueConstraint("collection_track_ranking_id", "lang", name="uq_ctr_locale"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    collection_track_ranking_id: int = Field(
        sa_column=Column(
            ForeignKey("collection_track_ranking.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    lang: str
    intro_text: str
    tts_key: Optional[str] = None

    ranking: "CollectionTrackRanking" = Relationship(
        sa_relationship=sa_relationship(
            "CollectionTrackRanking",
            back_populates="locales",
        )
    )
