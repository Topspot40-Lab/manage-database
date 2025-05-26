from fastapi import APIRouter, HTTPException, Path
from utils.json_helpers import load_json, REQUIRED_FIELDS
from shared.filepaths import get_json_path



router = APIRouter(prefix="", tags=["json-validate"])

@router.get("/validate-json/{decade}/{genre}")
def validate_json(
    decade: str = Path(...), genre: str = Path(...)
):
    try:
        # Assume language is English and filename follows format: {decade}_{genre}_en.json
        filename = f"{decade}_{genre}_en.json"
        filepath = Path(get_json_path(decade, genre, "en"))
        data = load_json(decade, filename)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {filepath}")
    except Exception as e:
        raise HTTPException(500, f"Read error: {e}")

    tracks = data.get("ranking_tables", {}).get("trackranking", [])
    missing_required = []
    for i, t in enumerate(tracks):
        missing = [f for f in REQUIRED_FIELDS if f not in t or t[f] in (None, "")]
        if missing:
            missing_required.append({
                "rank": t.get("rank", i + 1),
                "trackName": t.get("trackName", t.get("track_name", "Unknown")),
                "missing": missing
            })

    return {
        "status": "error" if missing_required else "success",
        "totalTracks": len(tracks),
        "errors": missing_required
    }
