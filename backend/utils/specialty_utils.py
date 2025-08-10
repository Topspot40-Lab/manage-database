# backend/utils/specialty_utils.py
from typing import Optional, Tuple, TYPE_CHECKING
from sqlmodel import Session, select
from sqlalchemy import and_

if TYPE_CHECKING:
    # Only for type checkers; avoids runtime import cycles
    from backend.models import Genre

def resolve_labels(data: dict, default_category: str, default_specialty: str) -> Tuple[str, str]:
    """
    Decide final (genre, category) consistently.
    genre: JSON['genre'] → default_specialty
    category: JSON['category'] → decade[0]['decade_name'] → default_category
    """
    genre = data.get("genre") or default_specialty

    category = data.get("category")
    if not category:
        decade = data.get("decade")
        if isinstance(decade, list) and decade and isinstance(decade[0], dict):
            category = decade[0].get("decade_name")
    category = category or default_category

    return genre, category


def parse_featured_keys(track: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract featured artist identifiers from a track dict.
    Supports: featured_artist_id / featured_artist_sid / featured_artist / featured_artist_name
    """
    feat_sid = track.get("featured_artist_id") or track.get("featured_artist_sid")
    feat_name = (track.get("featured_artist") or track.get("featured_artist_name") or "").strip() or None
    return feat_sid, feat_name


def should_update(existing_text: Optional[str], preserve_flag: bool) -> bool:
    """
    True if we should overwrite a text field, given the preserve flag.
    - preserve_flag=False → always update
    - preserve_flag=True → update only if existing is empty/whitespace/None
    """
    if not preserve_flag:
        return True
    return not (existing_text or "").strip()


def ensure_artist_genre_link(db: Session, artist_id: int, genre_row: Optional["Genre"]) -> None:
    """
    Create ArtistGenre(artist_id, genre_id) if missing. No-op if genre_row is None.
    Imports models lazily to prevent circular import issues.
    """
    if not genre_row:
        return

    # Lazy imports to avoid circular dependencies at import time
    from backend.models import ArtistGenre  # pylint: disable=import-outside-toplevel

    exists = db.exec(
        select(ArtistGenre).where(
            and_(ArtistGenre.artist_id == artist_id, ArtistGenre.genre_id == genre_row.id)
        )
    ).first()
    if not exists:
        db.add(ArtistGenre(artist_id=artist_id, genre_id=genre_row.id))
