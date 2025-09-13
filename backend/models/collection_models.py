from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import UniqueConstraint

class Collection(SQLModel, table=True):
    __tablename__ = "collection"
    __table_args__ = (UniqueConstraint("slug", name="uq_collection_slug"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True)
    intro: Optional[str] = None

    rankings: List["CollectionTrackRanking"] = Relationship(
        back_populates="collection",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

class CollectionTrackRanking(SQLModel, table=True):
    __tablename__ = "collection_track_ranking"
    __table_args__ = (
        UniqueConstraint("collection_id", "track_id", name="uix_ctr_collection_track"),
        UniqueConstraint("collection_id", "ranking",  name="uix_ctr_collection_rank"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    collection_id: int = Field(foreign_key="collection.id", index=True)
    track_id: int = Field(foreign_key="track.id", index=True)
    ranking: int = Field(index=True)
    intro: Optional[str] = None

    collection: "Collection" = Relationship(back_populates="rankings")
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
    lang: str
    intro_text: str
    tts_key: Optional[str] = None

    ranking: "CollectionTrackRanking" = Relationship(back_populates="locales")
