# backend/routers/collections_generate_json.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, text
from backend.database import get_db

# ✅ Use your existing spotify_service module
from backend.services.spotify_service import enrich_track_from_spotify

# Optional curate service (XAI). If not present yet, we return 501.
try:
    from backend.services.curate import curate_tracks_via_xai
except Exception:
    curate_tracks_via_xai = None  # type: ignore

router = APIRouter(prefix="/collections", tags=["Collections (Generate JSON)"])

def _sch(db: Session) -> str:
    """Use 'public.' on Postgres; '' otherwise to silence linters in tests/SQLite."""
    try:
        return "public." if db.get_bind().dialect.name.startswith("postgres") else ""
    except Exception:
        return ""

@router.get("/{slug}/generate-json")
def generate_json_for_collection(
    slug: str,
    target_count: int = Query(45, ge=1, le=100),
    db: Session = Depends(get_db),
):
    sch = _sch(db)

    # 1) Get collection meta
    coll = db.exec(
        text(f"""
            SELECT name, slug, collection_type, intro
            FROM {sch}v_collections_unified
            WHERE slug = :slug
            LIMIT 1
        """),
        params={"slug": slug}
    ).mappings().first()
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")

    # 2) Curate candidate tracks via XAI (title/artist/year)
    if curate_tracks_via_xai is None:
        raise HTTPException(
            status_code=501,
            detail="curate_tracks_via_xai not available. Create backend/services/curate.py "
                   "with a function curate_tracks_via_xai(theme, max_items) → List[Dict]."
        )
    theme = coll["name"]
    candidates = curate_tracks_via_xai(theme=theme, max_items=target_count)  # must return dicts with title/artist[/year]

    # 3) Enrich each candidate from Spotify using your service
    enriched = []
    for cand in candidates[:target_count]:
        title = cand.get("title")
        artist = cand.get("artist") or cand.get("artistName")
        year = cand.get("year")

        if not title or not artist:
            # Skip bad candidates instead of throwing
            continue

        # Your service function should return Spotify data for this title/artist[/year].
        e = enrich_track_from_spotify(title=title, artist=artist, year=year)

        # Normalize into the fields your JSON expects
        enriched.append({
            "title": e.get("title", title),
            "artist": e.get("artist", artist),
            "year": e.get("year", year),
            "spotify_track_id": e.get("spotify_track_id") or e.get("id"),
            "album_name": e.get("album_name") or (e.get("album", {}) or {}).get("name"),
            "album_art_url": (
                e.get("album_art_url")
                or (((e.get("album", {}) or {}).get("images") or [{}])[0].get("url"))
            ),
        })

    # 4) Shape TopSpot JSON
    payload = {
        "collection": {
            "name": coll["name"],
            "slug": coll["slug"],
            "type": coll["collection_type"],
            **({"intro": coll["intro"]} if coll.get("intro") else {})
        },
        "tracks": [
            {
                "ranking": i + 1,
                "title": t["title"],
                "artistName": t["artist"],
                "year": t.get("year"),
                "spotifyTrackId": t.get("spotify_track_id"),
                "albumName": t.get("album_name"),
                "albumArtUrl": t.get("album_art_url"),
            }
            for i, t in enumerate(enriched[:target_count])
        ],
    }
    return payload
