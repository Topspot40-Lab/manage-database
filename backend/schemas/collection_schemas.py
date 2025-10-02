# backend/schemas/collection_schemas.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, AliasChoices
from pydantic.config import ConfigDict  # pydantic v2

# ----- Collection -----
class CollectionIn(BaseModel):
    name: str
    slug: str
    intro: Optional[str] = None
    type: Optional[str] = None  # legacy; accepted but ignored

# ----- Import payload (single permissive track model) -----
class CollectionImportTrack(BaseModel):
    # keep extra fields, accept aliases/camelCase, and populate by field name
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # required
    ranking: int = Field(..., ge=1, validation_alias=AliasChoices("ranking", "rank"))

    intro: Optional[str] = Field(default=None, validation_alias=AliasChoices("intro", "note"))

    # identifiers (we’ll prefer trackId, then spotifyTrackId)
    trackId: Optional[int] = Field(default=None, ge=1, validation_alias=AliasChoices("trackId", "track_id"))
    spotifyTrackId: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("spotifyTrackId", "spotify_track_id", "spotify_id", "id"),
    )

    # metadata (optional; used for resolver/creation & display)
    title: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("title", "track_name", "trackTitle", "track", "trackName", "track_title"),
    )
    artistName: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("artistName", "artist_name", "artistDisplayName", "artist", "artist_display_name"),
    )
    year: Optional[int] = Field(default=None, validation_alias=AliasChoices("year", "yearReleased", "year_released"))

    # duet/new-format extras (harmless to keep)
    featured_artist_name: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("featured_artist_name", "featuredArtist", "featured_artist")
    )
    featured_artist_sid: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("featured_artist_sid", "featuredArtistId", "featured_artist_id")
    )
    mode_flag: Optional[str] = Field(default="SOLO", validation_alias=AliasChoices("mode_flag", "modeFlag"))
    duration_ms: Optional[int] = Field(default=None, validation_alias=AliasChoices("duration_ms", "durationMs"))
    album_artwork: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("album_artwork", "albumArtwork", "albumArtUrl", "album_art_url")
    )

class CollectionImportPayload(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    collection: CollectionIn
    tracks: List[CollectionImportTrack]
    dry_run: bool = False
    strict: bool = False
    replace: bool = False
    # accept both casing styles for this flag:
    skipResolve: bool = Field(default=False, validation_alias=AliasChoices("skipResolve", "skip_resolve"))

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
