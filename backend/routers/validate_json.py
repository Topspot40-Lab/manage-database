import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Path
from backend.utils.json_helpers import load_json


router = APIRouter(prefix="", tags=["json-validate"])

REQUIRED_FIELDS_TRACK_RANKING = [
    "track_name",
    "artist_name",
    "spotify_track_id",
    "genre",
    "decade",
    "rank",
    "intro",
    "ranking_date"
]

@router.get("/validate-json/{decade}/{genre}")
def validate_json(
    decade: str = Path(...),
    genre: str = Path(...)
):
    filename = f"{decade}_{genre}_en.json"
    full_path = Path("data/tracks") / decade / filename
    logging.info(f"Validating JSON file at: {full_path.resolve()}")

    try:
        data = load_json(decade, filename)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {filename}")
    except Exception as e:
        raise HTTPException(500, f"Read error for {filename}: {e}")

    tracks = data.get("ranking_tables", {}).get("track_ranking", [])
    missing_required = []
    for i, t in enumerate(tracks):
        missing = [f for f in REQUIRED_FIELDS_TRACK_RANKING if f not in t or t[f] in (None, "")]
        if missing:
            missing_required.append({
                "rank": t.get("rank", i + 1),
                "track_name": t.get("track_name", "Unknown"),
                "missing": missing
            })

    return {
        "status": "error" if missing_required else "success",
        "total_tracks": len(tracks),
        "errors": missing_required
    }
