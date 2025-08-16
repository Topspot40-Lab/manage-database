# backend/services/supabase_storage.py

import logging
from typing import Iterable, List, Dict
from backend.services.supabase_client import supabase
from backend.utils.tts_diagnostics import normalize_for_filename
from backend.utils.storage_keys import bucket_for  # uses your BUCKETS map

logger = logging.getLogger(__name__)

from io import BytesIO

def upload_bytes(bucket: str, key: str, data: bytes, content_type: str = "audio/mpeg"):
    """Upload or overwrite an object."""
    supabase.storage.from_(bucket).upload(
        path=key,
        file=BytesIO(data),
        file_options={
            "content-type": content_type,
            "cache-control": "public, max-age=31536000, immutable",
            "upsert": "true",
        },
    )

def object_exists(bucket: str, key: str) -> bool:
    """Lightweight existence check by listing the parent folder."""
    parent = key.rsplit("/", 1)[0] if "/" in key else ""
    name = key.split("/")[-1]
    objs = supabase.storage.from_(bucket).list(
        path=parent,
        limit=1000,
        sort_by={"column": "name", "order": "asc"},
        search=name,  # narrows results
    )
    return any(o.get("name") == name for o in (objs or []))


def _list_names_with_prefix(bucket: str, prefix: str, page_size: int = 1000) -> List[str]:
    """
    Returns object names in `bucket` whose name starts with `prefix`.
    Uses client-side filtering after listing; repeat with offset to cover >page_size.
    """
    names: List[str] = []
    offset = 0
    while True:
        # NOTE: supabase-py v2 list() returns a list of dicts like {"name": "...", ...}
        objs = supabase.storage.from_(bucket).list(
            path="",
            limit=page_size,
            offset=offset,
            sort_by={"column": "name", "order": "asc"},
        )
        if not objs:
            break
        batch = [o.get("name", "") for o in objs if o.get("name", "").startswith(prefix)]
        names.extend(batch)
        if len(objs) < page_size:
            break
        offset += page_size
    return names

def delete_mp3s_by_prefix(
    kind: str,                      # "intro" | "detail" | "artist"
    decade: str,
    genre: str,
    languages: Iterable[str],       # e.g. ["en"] or ["es","pt-BR"]
    dry_run: bool = True
) -> Dict[str, Dict]:
    """
    Deletes all objects whose name starts with '<decade>_<genre>_' from the
    language-specific bucket for the given `kind`.

    Returns a small report per language.
    """
    # Build the filename prefix used by your keys: {decade}_{genre}_{rank:02d}.mp3
    prefix = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_"
    report: Dict[str, Dict] = {}

    for lang in languages:
        bucket = bucket_for(kind, lang)   # maps pt-BR -> pt buckets for you
        matches = _list_names_with_prefix(bucket, prefix)

        logger.info(f"🧹 {kind.upper()} | lang={lang} bucket={bucket} prefix='{prefix}' matches={len(matches)}")
        if dry_run or not matches:
            report[lang] = {"bucket": bucket, "matched": len(matches), "deleted": 0, "dry_run": dry_run}
            continue

        # Supabase Storage remove() expects a list of paths (names)
        supabase.storage.from_(bucket).remove(matches)
        report[lang] = {"bucket": bucket, "matched": len(matches), "deleted": len(matches), "dry_run": False}

    return report

# Convenience wrappers if you still want single-purpose helpers:
def delete_intro_mp3_files_for_combo(decade: str, genre: str, languages: Iterable[str] = ("en", "es", "pt-BR"), dry_run: bool = True):
    return delete_mp3s_by_prefix("intro", decade, genre, languages, dry_run)

def delete_detail_mp3_files_for_combo(decade: str, genre: str, languages: Iterable[str] = ("en", "es", "pt-BR"), dry_run: bool = True):
    return delete_mp3s_by_prefix("detail", decade, genre, languages, dry_run)

def delete_artist_mp3_files_for_combo(decade: str, genre: str, languages: Iterable[str] = ("en", "es", "pt-BR"), dry_run: bool = True):
    return delete_mp3s_by_prefix("artist", decade, genre, languages, dry_run)
