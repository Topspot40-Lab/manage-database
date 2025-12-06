from backend.config import SUPABASE_URL

def build_public_audio_url(bucket: str, key: str) -> str:
    """
    Safely builds a public Supabase Storage URL.
    """
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{key}"
