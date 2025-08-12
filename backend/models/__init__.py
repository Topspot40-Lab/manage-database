# backend/models/__init__.py
from .dbmodels import (
    Genre,
    Decade,
    Artist,
    Track,
    TrackRanking,
    DecadeGenre,
    ArtistGenre,
    Specialty,
    SpecialtyRanking,
    Category,            # ✅ add
    SpecialtyCategory,   # ✅ add
    Language,            # ✅ (optional but useful)
    Tracklist,
    Top40GenreRanking,
    DecadeGenreTrivia,
    TrackGenre,
)

__all__ = [
    "Genre",
    "Decade",
    "Artist",
    "Track",
    "TrackRanking",
    "DecadeGenre",
    "ArtistGenre",
    "Specialty",
    "SpecialtyRanking",
    "Category",           # ✅ add
    "SpecialtyCategory",  # ✅ add
    "Language",           # ✅ add
    "Tracklist",
    "Top40GenreRanking",
    "DecadeGenreTrivia",
    "TrackGenre",
]
