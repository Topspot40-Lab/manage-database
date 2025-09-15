from __future__ import annotations
from typing import TYPE_CHECKING

from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import UniqueConstraint, CheckConstraint

if TYPE_CHECKING:
    # Simple stubs so the type checker knows these names exist.
    # No runtime effect; not imported/circular.
    class Collection(SQLModel): ...
    class CollectionTrackRankingLocale(SQLModel): ...

class CollectionTrackRanking(SQLModel, table=True):
    __tablename__ = "collection_track_ranking"
    __table_args__ = (
        UniqueConstraint("collection_id", "track_id", name="uix_ctr_collection_track"),
        UniqueConstraint("collection_id", "ranking",  name="uix_ctr_collection_rank"),
        CheckConstraint("ranking > 0", name="ck_ctr_ranking_positive"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # Works with recent SQLModel: ondelete + foreign_key + index
    collection_id: int = Field(
        foreign_key="collection.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
    )
    track_id: int = Field(
        foreign_key="track.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
    )
    ranking: int = Field(index=True)
    intro: Optional[str] = None

    collection: "Collection" = Relationship(back_populates="rankings")
    locales: List["CollectionTrackRankingLocale"] = Relationship(
        back_populates="ranking",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
