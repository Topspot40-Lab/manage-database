# backend/services/spotify/enrich_artist_artwork.py
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger(__name__)

def _sp_client() -> Spotify:
    # Uses SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET envs (already in your config)
    return Spotify(auth_manager=SpotifyClientCredentials())

def _best_image_url(images: List[dict]) -> Optional[str]:
    # Spotify returns largest first; be defensive
    if not images:
        return None
    return images[0].get("url") or None

def _normalize(name: str) -> str:
    return (name or "").strip().lower()

def _extract_artist_id_from_tracks(tracks: List[dict]) -> Dict[str, str]:
    """
    Build a map: artist_name(lower) -> spotify_artist_id
    Pull from any track-level Spotify payload you have after STEP 3.
    """
    mapping: Dict[str, str] = {}
    for t in tracks or []:
        artist_name = _normalize(t.get("artist_name"))
        # Prefer explicit artist id if present on the track enrichment
        aid = t.get("spotify_artist_id") or t.get("artist_id") or None
        if artist_name and aid and artist_name not in mapping:
            mapping[artist_name] = aid
        # Fallback: if we have a full 'spotify_artist' object in the track payload
        sp_artist_obj = t.get("spotify_artist")  # if your enrich step attached it
        if artist_name and not mapping.get(artist_name) and isinstance(sp_artist_obj, dict):
            aid2 = sp_artist_obj.get("id")
            if aid2:
                mapping[artist_name] = aid2
    return mapping

def _search_artist_id(sp: Spotify, name: str) -> Optional[str]:
    try:
        q = f'artist:"{name}"'
        res = sp.search(q=q, type="artist", limit=1)
        items = (res or {}).get("artists", {}).get("items", [])
        if items:
            return items[0].get("id")
    except Exception as e:
        logger.warning("Spotify search failed for %r: %s", name, e)
    return None

def enrich_artist_table_with_spotify(
    artist_table: List[dict],
    tracks_after_step3: List[dict],
    *,
    fill_missing_ids_via_search: bool = True
) -> List[dict]:
    """
    For each artist:
      - Ensure spotify_artist_id (from tracks; optional search if allowed)
      - Fetch Spotify artist and set artist_artwork (largest image URL)
      - Leave existing fields intact
    """
    if not artist_table:
        return artist_table

    sp = _sp_client()

    # Build authoratitive id map from enriched tracks
    name_to_id = _extract_artist_id_from_tracks(tracks_after_step3)

    for a in artist_table:
        name_norm = _normalize(a.get("artist_name"))
        aid = a.get("spotify_artist_id") or name_to_id.get(name_norm)

        # Optional: search to fill missing id
        if not aid and fill_missing_ids_via_search and name_norm:
            aid = _search_artist_id(sp, a.get("artist_name"))
            if aid:
                a["spotify_artist_id"] = aid

        if not aid:
            # No ID → we can’t fetch images; move on gracefully
            continue

        # Fetch artist object → get images
        try:
            sp_artist = sp.artist(aid)
            img = _best_image_url(sp_artist.get("images") or [])
            if img:
                a["artist_artwork"] = img
        except Exception as e:
            logger.warning("Failed to fetch artist %s (%s): %s", a.get("artist_name"), aid, e)

    return artist_table
