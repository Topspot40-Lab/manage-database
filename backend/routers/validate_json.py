from fastapi import APIRouter, HTTPException, Path
from utils.json_helpers import load_json, REQUIRED_FIELDS

router = APIRouter(prefix="", tags=["json-validate"])

@router.get("/validate-json/{decade}/{filename}")
def validate_json(
    decade: str = Path(...), filename: str = Path(...)
):
    try:
        data = load_json(decade, filename)
    except FileNotFoundError:
        raise HTTPException(404, "File not found")
    except Exception as e:
        raise HTTPException(500, f"Read error: {e}")

    tracks = data.get("ranking_tables", {}).get("trackranking", [])
    errors = [
        {
            "rank": t.get("rank", i + 1),
            "trackName": t.get("trackName", "Unknown"),
            "missing": [f for f in REQUIRED_FIELDS if f not in t],
        }
        for i, t in enumerate(tracks)
        if any(f not in t for f in REQUIRED_FIELDS)
    ]

    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "success", "totalTracks": len(tracks)}
