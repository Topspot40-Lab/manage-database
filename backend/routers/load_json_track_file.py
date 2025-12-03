# backend/routers/load_json_track_file.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.track_cache import load_tracks_from_file
from backend.config import BASE_DIR

import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/json", tags=["JSON & Files"])


class FileLoadRequest(BaseModel):
    genre: str
    decade: str

@router.post("/load-json-track-file")
def load_json_track_file(request: FileLoadRequest):

    print(f"🧭 Entering load_json_track_file endpoint")
    genre = request.genre.lower()
    decade = request.decade.lower()

    filename = f"{decade}_{genre}_en.json"

    file_path = (
        BASE_DIR / "topspot_json_creator" / "data" / "json_files" /
        "genredecade" / decade / filename
    )

    print(f"🧭 Loading from: {file_path.resolve()}")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    success = load_tracks_from_file(filename, file_path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to load file.")

    return {
        "message": f"✅ Loaded file: {filename}",
        "path": str(file_path)
    }
