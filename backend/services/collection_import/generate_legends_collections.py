"""
generate_legends_collections.py
Builds “Top 40 Legends” collections automatically.

For each genre (Country, Pop, Rock, etc.):
  • Calculates a score per artist across all decades
  • Selects one representative track (their best-ranked)
  • Creates/updates a “Legends – {Genre}” collection
  • Populates 40 ranked entries in collection_track_ranking
"""

from typing import List, Tuple, Optional

from sqlalchemy import asc, desc, delete
from sqlmodel import Session, select, func

from backend.database import get_db_session
from backend.models import (
    Genre,
    Track,
    TrackRanking,
    Collection,
    CollectionCategory,
    CollectionTrackRanking,
)

# ────────────────────────────────────────────────
# CONFIGURATION
# ────────────────────────────────────────────────
LEGENDS_CATEGORY_NAME = "Music Legends"
LEGENDS_CATEGORY_SLUG = "music_legends"

# Generate all eight Legends collections
LEGENDS_GENRES = [
    "Country",
    "Pop",
    "Rock",
    "TV Themes",
    "RnB Soul",
    "Latin Global",
    "Blues Jazz",
    "Folk Acoustic",
]

MAX_RANK = 45


# ────────────────────────────────────────────────
def get_or_create_category(db: Session) -> CollectionCategory:
    """Ensure the Music Legends category exists."""
    category = db.exec(
        select(CollectionCategory).where(CollectionCategory.slug == LEGENDS_CATEGORY_SLUG)
    ).first()
    if not category:
        category = CollectionCategory(
            name=LEGENDS_CATEGORY_NAME,
            slug=LEGENDS_CATEGORY_SLUG,
            sort_order=10,
            intro="Top 40 legends by genre across all decades.",
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        print(f"✅ Created category '{category.name}'")
    return category


def get_or_create_legends_collection(db: Session, category: CollectionCategory, genre_name: str) -> Collection:
    """Ensure a Legends collection exists for this genre."""
    slug = f"legends_{genre_name.lower().replace(' ', '_')}"
    name = f"Legends – {genre_name}"
    collection = db.exec(select(Collection).where(Collection.slug == slug)).first()
    if not collection:
        collection = Collection(
            name=name,
            slug=slug,
            intro=f"Top 40 {genre_name} legends across all decades.",
            category_id=category.id,
            sort_order=0,
        )
        db.add(collection)
        db.commit()
        db.refresh(collection)
        print(f"🎶 Created collection '{name}'")
    return collection


def compute_artist_scores(db: Session, genre_id: int) -> List[Tuple[int, float, int]]:
    """
    Compute aggregate artist scores for a genre via TrackRanking → DecadeGenre → Genre.
    """
    from backend.models.dbmodels import DecadeGenre

    results = db.exec(
        select(
            Track.artist_id,
            func.sum(41 - TrackRanking.ranking).label("score"),
            func.count(Track.id).label("num_tracks"),
        )
        .join(Track, Track.id == TrackRanking.track_id)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .where(DecadeGenre.genre_id == genre_id, TrackRanking.ranking <= MAX_RANK)
        .group_by(Track.artist_id)
        .order_by(desc(func.sum(41 - TrackRanking.ranking)))
    ).all()
    return results


def find_best_track_for_artist(db: Session, artist_id: int, genre_id: int) -> Optional[Track]:
    """Find the highest-ranked (lowest ranking) track for an artist in this genre."""
    from backend.models.dbmodels import DecadeGenre

    return db.exec(
        select(Track)
        .join(TrackRanking, Track.id == TrackRanking.track_id)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .where(Track.artist_id == artist_id, DecadeGenre.genre_id == genre_id)
        .order_by(asc(TrackRanking.ranking))
        .limit(1)
    ).first()


def clear_collection_entries(db: Session, collection_id: int) -> None:
    """Remove existing rows for a legends collection before re-populating."""
    db.exec(delete(CollectionTrackRanking).where(CollectionTrackRanking.collection_id == collection_id))
    db.commit()


def populate_legends_collection(db: Session, collection: Collection, genre_id: int) -> None:
    """Build or refresh the legends list for one genre."""
    print(f"\n🏆 Generating legends for {collection.name} …")

    artist_scores = compute_artist_scores(db, genre_id)
    top_artists = artist_scores[:MAX_RANK]

    # Clear old entries
    clear_collection_entries(db, collection.id)

    added = 0
    for rank, (artist_id, score, _num_tracks) in enumerate(top_artists, start=1):
        track = find_best_track_for_artist(db, artist_id, genre_id)
        if not track:
            continue

        genre_label = collection.name.replace("Legends – ", "").strip()
        track_name = track.track_name
        artist_name = track.artist_display_name or "this legendary artist"

        intro = (
            f"And now at number {rank} in the Legends {genre_label} collection, "
            f"we have \"{track_name}\" by {artist_name}."
        )

        ctr = CollectionTrackRanking(
            collection_id=collection.id,
            track_id=track.id,
            ranking=rank,
            intro=intro,
        )
        db.add(ctr)
        added += 1
        print(f"   #{rank:02d}: {track.track_name} — artist_id={artist_id} ({int(score)} pts)")

    db.commit()
    print(f"✅ Completed {collection.name} — inserted {added} rows")


def run_generate_legends() -> None:
    with get_db_session() as db:
        category = get_or_create_category(db)

        for genre_name in LEGENDS_GENRES:
            # Adjust if your Genre model uses a different field than `genre_name`
            genre = db.exec(
                select(Genre).where(func.lower(Genre.genre_name) == genre_name.lower())
            ).first()
            if not genre:
                print(f"⚠️  Skipping {genre_name} (genre not found in DB)")
                continue

            collection = get_or_create_legends_collection(db, category, genre_name)
            populate_legends_collection(db, collection, genre.id)

        print("\n🎉 All legends collections generated successfully!")


if __name__ == "__main__":
    run_generate_legends()
