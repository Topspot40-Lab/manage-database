from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

def _resolve_client():
    # Prefer a factory if present, else a singleton
    try:
        from backend.services.supabase_client import get_client
        return get_client()
    except Exception:
        try:
            from backend.services.supabase_client import supabase
            return supabase
        except Exception:
            return None

def sign_url(bucket: str | None, key: str | None, expires: int = 300) -> str | None:
    """Create a temporary public URL for a file in Supabase Storage."""
    if not bucket or not key:
        return None
    client = _resolve_client()
    if not client:
        logger.warning("Supabase client unavailable; cannot sign %s/%s", bucket, key)
        return None
    try:
        res = client.storage.from_(bucket).create_signed_url(key, expires)
        return res.get("signedURL") or res.get("signed_url")
    except Exception as e:
        logger.warning("Sign failed for %s/%s: %s", bucket, key, e)
        return None
