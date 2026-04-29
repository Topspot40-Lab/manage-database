from sqlmodel import Session, select

from backend.database import engine
from backend.models import CollectionTrackRanking, Collection, Track


TEMPLATES = [
    'And now at number {rank} in the {collection} collection, we have "{track}" by {artist}.',
    'Coming in at number {rank} in the {collection} collection, we have "{track}" by {artist}.',
    'At number {rank} in the {collection} collection, here is "{track}" by {artist}.',
    'Sliding into the number {rank} spot in the {collection} collection, it is "{track}" by {artist}.',
    'Holding down number {rank} in the {collection} collection, we have "{track}" by {artist}.',
    'Up next at number {rank} in the {collection} collection, we have "{track}" by {artist}.',
]


def main() -> None:
    updated = 0

    with Session(engine) as session:
        rows = session.exec(
            select(CollectionTrackRanking)
            .where(CollectionTrackRanking.collection_id >= 21)
            .where(CollectionTrackRanking.collection_id <= 28)
            .order_by(CollectionTrackRanking.collection_id, CollectionTrackRanking.ranking)
        ).all()

        for row in rows:
            collection = session.get(Collection, row.collection_id)
            track = session.get(Track, row.track_id)

            if collection is None or track is None:
                print(f"Skipping row id={row.id}: missing collection or track")
                continue

            artist = track.artist_display_name or "this legendary artist"
            template = TEMPLATES[row.ranking % len(TEMPLATES)]

            row.intro = template.format(
                rank=row.ranking,
                collection=collection.name,
                track=track.track_name,
                artist=artist,
            )

            session.add(row)
            updated += 1

        session.commit()

    print(f"✅ Updated {updated} Legends intro rows.")


if __name__ == "__main__":
    main()