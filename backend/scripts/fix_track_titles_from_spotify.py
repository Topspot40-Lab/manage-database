import argparse
from sqlmodel import Session, select

from backend.database import engine
from backend.models import Track
from backend.services.spotify_service import get_spotify_client


def looks_suspicious(name: str | None) -> bool:
    if not name:
        return False

    stripped = name.strip()

    # Only target obvious lowercase-style titles.
    return stripped == stripped.lower() and any(ch.isalpha() for ch in stripped)


def get_spotify_title(spotify_track_id: str) -> str | None:
    try:
        sp = get_spotify_client()
        track = sp.track(spotify_track_id)
        return track.get("name")
    except Exception as exc:
        print(f"⚠️ Spotify lookup failed for {spotify_track_id}: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    changed = 0
    checked = 0

    with Session(engine) as session:
        tracks = session.exec(
            select(Track)
            .where(Track.spotify_track_id != None)
            .order_by(Track.id)
        ).all()

        for track in tracks:
            if checked >= args.limit:
                break

            if not looks_suspicious(track.track_name):
                continue

            checked += 1
            spotify_title = get_spotify_title(track.spotify_track_id)

            if not spotify_title or spotify_title == track.track_name:
                continue

            print(f'{track.id}: "{track.track_name}" -> "{spotify_title}"')

            if args.apply:
                track.track_name = spotify_title
                session.add(track)
                changed += 1

        if args.apply:
            session.commit()

    print(f"\nChecked suspicious titles: {checked}")
    print(f"Updated titles: {changed}")
    print("Mode:", "APPLY" if args.apply else "DRY RUN")


if __name__ == "__main__":
    main()