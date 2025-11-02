# backend/services/spotify/backfill_artists.py
"""
Backfill missing Spotify artist IDs and/or artwork for artists.

Modes:
- default: find artists missing spotify_artist_id (skips multi-artist names) and fill id+artwork
- --only:   operate on specific artist IDs
- --artwork-only: fill missing artist_artwork for rows that already have spotify_artist_id
"""
from __future__ import annotations
import logging
import re
from typing import Iterable, Optional, List

from sqlmodel import select
from backend.database import get_db_session
from backend.models.dbmodels import Artist
from backend.services.spotify.spotify_auth_user import get_spotify_user_client

logger = logging.getLogger("spotify_backfill")
_APOSTROPHE_VARIANTS = ["'", "’", "ʻ"]  # straight, curly, okina

def _strip_parenthetical(s: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", s or "").strip()

def _collapse_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _ascii_apostrophe_variants(name: str) -> list[str]:
    base = _collapse_whitespace(_strip_parenthetical(name))
    variants = {base}
    for src in _APOSTROPHE_VARIANTS:
        variants.add(base.replace(src, "'"))
        variants.add(base.replace(src, "’"))
        variants.add(base.replace(src, "ʻ"))
        variants.add(base.replace(src, ""))  # drop apostrophes entirely
    v2 = set()
    for v in variants:
        v2.add(v)
        v2.add(v.lower())
        v2.add(v.title())
    return [x for x in v2 if x]

def _search_artist(sp, name: str) -> Optional[dict]:
    tried = []
    for qname in _ascii_apostrophe_variants(name):
        for q in (f'artist:"{qname}"', qname):
            tried.append(q)
            try:
                res = sp.search(q=q, type="artist", limit=1)
                items = res.get("artists", {}).get("items", [])
                if items:
                    return items[0]
            except Exception as e:
                logger.debug("search error for %r -> %s", q, e)
    logger.warning("⚠️ No Spotify match for %r (tried %s)", name, ", ".join(tried[:4]) + ("…" if len(tried) > 4 else ""))
    return None

def _update_artist_record(db, artist: Artist, info: dict) -> None:
    artist.spotify_artist_id = info.get("id")
    imgs = info.get("images") or []
    artist.artist_artwork = imgs[0]["url"] if imgs else None
    db.add(artist)

def _chunks(lst: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def backfill_artist_spotify_data(
    limit: int = 50,
    *,
    overrides: Iterable[int] | None = None,
    artwork_only: bool = False,
) -> None:
    """
    - artwork_only=True: fill only missing artist_artwork where spotify_artist_id is present.
    - otherwise: fill missing spotify_artist_id (and artwork), skipping obvious multi-artist rows.
    - overrides: run only for specific Artist.id values.
    """
    sp = get_spotify_user_client()

    with get_db_session() as db:
        if artwork_only:
            # Find artists with an ID but no artwork
            q = (
                select(Artist)
                .where(Artist.spotify_artist_id.is_not(None))
                .where((Artist.artist_artwork.is_(None)) | (Artist.artist_artwork == ""))
                .limit(limit)
            )
            targets: list[Artist] = db.exec(q).all()
            logger.info("🎯 Found %d artist(s) missing artwork (limit=%d)", len(targets), limit)

            # Batch fetch from Spotify
            id_map = {a.spotify_artist_id: a for a in targets if a.spotify_artist_id}
            spotify_ids = list(id_map.keys())
            updated = 0
            for batch in _chunks(spotify_ids, 50):
                try:
                    resp = sp.artists(batch)
                    for item in (resp.get("artists") or []):
                        artist_row = id_map.get(item.get("id"))
                        if not artist_row:
                            continue
                        imgs = item.get("images") or []
                        new_url = imgs[0]["url"] if imgs else None
                        if new_url:
                            artist_row.artist_artwork = new_url
                            db.add(artist_row)
                            updated += 1
                            logger.info("🖼️  Artwork set — %s: %s", artist_row.artist_name, new_url)
                except Exception as e:
                    logger.warning("⚠️ Batch artwork fetch failed for %s: %s", batch, e)

            db.commit()
            logger.info("🎧 Artwork-only backfill complete — %d updated.", updated)
            return

        # Normal mode: fill missing spotify_artist_id (and artwork)
        if overrides:
            missing = db.exec(
                select(Artist).where(Artist.id.in_(list(overrides)))
            ).all()
        else:
            missing = db.exec(
                select(Artist)
                .where(Artist.spotify_artist_id.is_(None))
                .where(Artist.artist_name.not_like('%,%'))
                .where(Artist.artist_name.not_like('%&%'))
                .where(Artist.artist_name.not_like('%feat.%'))
                .limit(limit)
            ).all()

        logger.info("🎯 Found %d artist(s) to backfill", len(missing))
        updated = 0
        for artist in missing:
            name = (artist.artist_name or "").strip()
            if not name:
                continue
            info = _search_artist(sp, name)
            if not info:
                continue
            _update_artist_record(db, artist, info)
            updated += 1
            logger.info("✅ %s — id=%s  artwork=%s",
                        artist.artist_name, artist.spotify_artist_id, artist.artist_artwork or "None")

        db.commit()
        logger.info("🎧 Backfill complete — %d updated.", updated)

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--only", type=int, nargs="*", help="Run only for these artist IDs")
    parser.add_argument("--artwork-only", action="store_true", help="Fill missing artist_artwork using existing spotify_artist_id")
    args = parser.parse_args()
    backfill_artist_spotify_data(limit=args.limit, overrides=args.only, artwork_only=args.artwork_only)
