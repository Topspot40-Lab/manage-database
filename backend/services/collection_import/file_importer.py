# backend/services/collection_import/file_importer.py
from __future__ import annotations
import json
from pathlib import Path
from fastapi import HTTPException
from sqlmodel import Session

import backend.config as cfg
from backend.schemas.collection_schemas import CollectionImportPayload, ImportResult, CollectionIn
from backend.services.collection_import.assembler import assemble_items
from backend.services.collection_import.collection_upsert import upsert_collection
from backend.services.collection_import.track_binding import ensure_tracks_for_items
from backend.services.collection_import.payload_importer import import_payload


def import_from_file(db: Session, slug: str, fill_missing_from_json: bool = False, prefer_json: bool = False) -> ImportResult:
    """Import a collection from JSON file located at data/json_files/collections/{slug}.json"""
    path = Path(cfg.BASE_DIR) / "data" / "json_files" / "collections" / f"{slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Collection JSON not found: {path}")

    doc = json.loads(path.read_text(encoding="utf-8"))
    coll_meta = doc.get("collection") or {}
    coll_name = coll_meta.get("name") or slug.replace("_", " ").title()
    coll_intro = coll_meta.get("intro") if isinstance(coll_meta.get("intro"), str) else None

    items, meta_by_spid, rank_to_spid, _rank_to_intro = assemble_items(doc)
    if not items:
        raise HTTPException(status_code=400, detail="No tracks found to import.")

    coll = upsert_collection(db, slug, coll_name, coll_intro)
    ensure_tracks_for_items(db, items, meta_by_spid, prefer_json)

    payload = CollectionImportPayload(collection=CollectionIn(name=coll_name, slug=slug, intro=coll_intro), tracks=items)
    result = import_payload(db, payload)

    return result
