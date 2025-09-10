# backend/schemas/collection_schemas.py
from __future__ import annotations
from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field

CollectionType = Literal["DECADE_GENRE", "SPECIALTY"]

class CollectionIn(BaseModel):
    name: str
    slug: str
    type: CollectionType
    notes: Optional[str] = None

class TrackItemById(BaseModel):
    ranking: int
    trackId: int = Field(..., ge=1)

class TrackItemByMeta(BaseModel):
    ranking: int
    title: str
    artistName: str
    year: Optional[int] = None

class CollectionImportPayload(BaseModel):
    collection: CollectionIn
    tracks: List[Union[TrackItemById, TrackItemByMeta]]
    # Optional behaviors
    dry_run: bool = False
    strict: bool = False  # if True, fail whole import if any unresolved

class CollectionExportTrack(BaseModel):
    ranking: int
    trackId: int
    title: str
    artistName: str
    year: Optional[int] = None

class CollectionExport(BaseModel):
    collection: CollectionIn
    tracks: List[CollectionExportTrack]

class ImportResult(BaseModel):
    collectionId: int
    inserted: int
    updated: int
    unresolved: list[dict]
    totalIncoming: int
    dry_run: bool
