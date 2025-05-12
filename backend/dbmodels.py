# backend/dbmodels.py

from sqlmodel import SQLModel, Field

class Track(SQLModel, table=True):
    trackID:      str  = Field(primary_key=True, index=True)
    trackName:    str
    artistName:   str
    yearReleased: int
    durationMs:   int     = Field(default=None)
    intro:        str     = Field(default=None)
    detail:       str     = Field(default=None)
