# backend/utils/storage_keys.py
from backend.config import BUCKETS
def bucket_for(kind: str, lang: str = "en") -> str:
    code = "pt" if lang in ("pt", "pt-BR") else lang
    return BUCKETS.get(code, BUCKETS["en"])[kind]

def key_for(decade: str, genre: str, rank: int) -> str:
    return f"{decade}_{genre}_{rank:02d}.mp3".lower().replace(" ", "_")
