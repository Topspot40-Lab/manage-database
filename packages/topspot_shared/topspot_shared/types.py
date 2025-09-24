# packages/topspot_shared/topspot_shared/types.py
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

Lang = Literal["en", "es", "pt-BR"]

class StorageKey(BaseModel):
    bucket: str
    key: str

class RankingEntry(BaseModel):
    rank: int
    trackName: str
    artistName: str

    # Optional localized texts
    intro: Optional[str] = None
    detail: Optional[str] = None
    artistDescription: Optional[str] = None

    # Optional audio keys
    introKey: Optional[StorageKey] = None
    detailKey: Optional[StorageKey] = None
    artistKey: Optional[StorageKey] = None

    # Optional artwork
    artistArtwork: Optional[str] = None
    albumArtwork: Optional[str] = None


class LoadDecadeGenreDataResponse(BaseModel):
    decade: str
    genre: str
    language: Lang
    track_count: int
    rankings: list[RankingEntry] = Field(default_factory=list)  # pyright: ignore[reportMutableDefault]


class PlayState(BaseModel):
    intro: bool
    detail: bool
    track: bool
    artist: bool

class PlayTrackByRankOnlyRequest(BaseModel):
    rank: int
    play_intro: bool = True
    play_detail: bool = True
    play_track: bool = True
    play_artist_description: bool = True
    tts_language: Lang = "en"

class PlayTrackByRankResult(BaseModel):
    status: Literal["success", "error"]
    decade: Optional[str] = None
    genre: Optional[str] = None
    rank: Optional[int] = None
    played: Optional[PlayState] = None
    error: Optional[str] = None
