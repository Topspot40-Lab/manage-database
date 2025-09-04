# backend/tools/emit_decade_json.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
from pathlib import Path

@dataclass
class TrackPick:
    rank: int
    decade: str               # e.g., "1950s"
    genre: str                # e.g., "Folk Acoustic"
    spotify_track_id: str
    track_name: str
    spotify_artist_id: str
    artist_name: str
    album_name: Optional[str] = None
    album_artwork: Optional[str] = None
    year_released: Optional[int] = None
    duration_ms: Optional[int] = None
    popularity: Optional[int] = None
    is_explicit: Optional[bool] = False
    featured_artist: Optional[str] = None
    featured_artist_id: Optional[str] = None
    mode_flag: str = "SOLO"   # "SOLO" | "DUET" | ...
    detail: str = ""          # your “track detail” narration text

@dataclass
class ArtistBio:
    spotify_artist_id: str
    artist_name: str
    artist_artwork: Optional[str] = None
    artist_description: str = ""
    not_on_spotify: bool = False

def emit_decade_file(
    *,
    language: str,                    # "english" | "spanish" | ...
    decade_name: str,                 # "1950s"..."2020s"
    genre_name: str,                  # "Folk Acoustic"
    tracks: List[TrackPick],
    artists: List[ArtistBio],
    out_path: Path
) -> Path:
    payload: Dict[str, Any] = {
        "language": language,
        "category": decade_name,      # matches your sample’s "category"
        "genre": genre_name,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "genre_table": [{"genre_name": genre_name}],
        "decade": [{"decade_name": decade_name}],
        "artist": [
            {
                "artist_name": a.artist_name,
                "spotify_artist_id": a.spotify_artist_id,
                "artist_artwork": a.artist_artwork,
                "artist_description": a.artist_description,
                "not_on_spotify": a.not_on_spotify,
            }
            for a in artists
        ],
        "track": [
            {
                "rank": t.rank,
                "track_name": t.track_name,
                "artist_name": t.artist_name,
                "artist_display_name": t.artist_name.title(),   # or your own casing fn
                "featured_artist": t.featured_artist,
                "featured_artist_id": t.featured_artist_id,
                "track_display_name": t.track_name,             # keep as-is (lowercase in sample)
                "genre": t.genre,
                "decade": t.decade,
                "spotify_track_id": t.spotify_track_id,
                "spotify_artist_id": t.spotify_artist_id,
                "mode_flag": t.mode_flag,
                "duration_ms": t.duration_ms,
                "popularity": t.popularity,
                "album_artwork": t.album_artwork,
                "album_name": t.album_name,
                "year_released": t.year_released,
                "is_explicit": bool(t.is_explicit),
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "detail": t.detail,                              # ⬅ matches your example
                # If you later decide to store intros alongside tracks, add:
                # "intro": t.intro_text,
            }
            for t in sorted(tracks, key=lambda x: x.rank)
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path
