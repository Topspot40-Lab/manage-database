# backend/models/__init__.py

from .dbmodels import (
    # taxonomy / linking
    Genre, Decade, DecadeGenre, ArtistGenre,
    # core entities
    Artist, Track, TrackRanking,
    # locales
    TrackRankingLocale, TrackLocale, ArtistLocale, Language,
)

__all__ = [
    # taxonomy / linking
    "Genre", "Decade", "DecadeGenre", "ArtistGenre",
    # core entities
    "Artist", "Track", "TrackRanking",
    # locales
    "TrackRankingLocale", "TrackLocale", "ArtistLocale", "Language",
]
