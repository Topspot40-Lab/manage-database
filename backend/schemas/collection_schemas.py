# backend/schemas/collection_schemas.py
from __future__ import annotations
from typing import List, Optional, Union
from pydantic import BaseModel, Field, AliasChoices

# ----- Collection -----

class CollectionIn(BaseModel):
    name: str
    slug: str
    intro: Optional[str] = None
    type: Optional[str] = None  # legacy; accepted but ignored

# ----- Import payload (track variants) -----

class TrackItemBase(BaseModel):
    ranking: int = Field(..., ge=1)
    # Accept either "intro" (preferred) OR legacy "note" in requests
    intro: Optional[str] = Field(default=None, validation_alias=AliasChoices("intro", "note"))

class TrackItemById(TrackItemBase):
    trackId: int = Field(..., ge=1)

class TrackItemByMeta(TrackItemBase):
    title: str
    artistName: str
    year: Optional[int] = None

class TrackItemBySpotifyId(TrackItemBase):
    spotifyTrackId: str

TrackItem = Union[TrackItemById, TrackItemBySpotifyId, TrackItemByMeta]

class CollectionImportPayload(BaseModel):
    collection: CollectionIn
    tracks: List[TrackItem]
    dry_run: bool = False
    strict: bool = False
    replace: bool = False
    skipResolve: bool = False

# ----- Export shapes -----

class CollectionExportTrack(BaseModel):
    ranking: int
    trackId: int
    title: str
    artistName: Optional[str] = None
    year: Optional[int] = None
    intro: Optional[str] = None  # always emit 'intro' in responses

class CollectionExport(BaseModel):
    collection: CollectionIn
    tracks: List[CollectionExportTrack]

# ----- Import result -----

class ImportResult(BaseModel):
    collectionId: int
    inserted: int
    updated: int
    unresolved: List[dict]
    totalIncoming: int
    dry_run: bool
