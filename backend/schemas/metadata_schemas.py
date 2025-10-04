from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict  # pydantic v2

class DecadeDesc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    slug: str
    description: Optional[str] = None

class GenreDesc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    slug: str
    description: Optional[str] = None

class DecadeGenreDesc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    decade: str
    genre: str
    description: Optional[str] = None

class SeedDoc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    decades: List[DecadeDesc] = Field(default_factory=list)
    genres: List[GenreDesc] = Field(default_factory=list)
    decade_genre: List[DecadeGenreDesc] = Field(default_factory=list, alias="decade_genre")
