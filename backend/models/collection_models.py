# backend/models/collection_models.py
from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class Collection(SQLModel, table=True):
    __tablename__ = "collection"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    collection_type: str  # 'DECADE_GENRE' | 'SPECIALTY'
    decade_id: Optional[int] = Field(default=None, foreign_key="decade.id")
    genre_id: Optional[int] = Field(default=None, foreign_key="genre.id")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    rankings: List["CollectionTrackRanking"] = Relationship(back_populates="collection")

class CollectionTrackRanking(SQLModel, table=True):
    __tablename__ = "collection_track_ranking"
    id: Optional[int] = Field(default=None, primary_key=True)
    collection_id: int = Field(foreign_key="collection.id")
    track_id: int = Field(foreign_key="track.id")
    ranking: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    collection: Optional[Collection] = Relationship(back_populates="rankings")
