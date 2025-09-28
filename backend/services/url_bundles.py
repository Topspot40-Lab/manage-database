from typing import Optional
from fastapi import Request
from backend.services.supabase_signer import sign_url
from backend.services.playback_helpers import bucket_for, key_for, build_detail_filename, build_artist_filename

def _signed(bucket: Optional[str], key: Optional[str], expires: int) -> Optional[str]:
    if not bucket or not key:
        return None
    return sign_url(bucket, key, expires)

def bundle_for_track(lang: str, *, track, artist, use_intro: bool, use_detail: bool,
                     use_artist: bool, expires: int, request: Request) -> dict:
    # no collection/decade intros here (keep generic)
    intros = []
    detail_url = None
    artist_url = None

    if use_detail:
        detail_fn  = build_detail_filename(track.spotify_track_id)
        if detail_fn:
            detail_url = _signed(bucket_for(lang, "detail"), key_for("detail", detail_fn), expires)

    if use_artist and getattr(artist, "spotify_artist_id", None):
        artist_fn = build_artist_filename(artist.spotify_artist_id)
        if artist_fn:
            artist_url = _signed(bucket_for(lang, "artist"), key_for("artist", artist_fn), expires)

    return {
        "spotify_track_id": track.spotify_track_id,
        "intros": intros,
        "detail": detail_url,
        "artist": artist_url,
        "track_name": track.track_name,
        "artist_name": artist.artist_name,
    }
