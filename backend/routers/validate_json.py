import logging
from pathlib import Path  # 🟢 Used for file paths
from fastapi import APIRouter, HTTPException, Path as FastAPIPath  # 🟢 Avoids name conflict
from backend.utils.json_helpers import load_json

logger = logging.getLogger(__name__)  # 🔧 Module-specific logger

router = APIRouter(prefix="", tags=["json-validate"])

REQUIRED_FIELDS_TRACK_RANKING = [
    "track_name",
    "artist_name",
    "spotify_track_id",
    "genre",
    "decade",
    "rank",
    # "intro",
    "ranking_date"
]

@router.get("/validate-json/{decade}/{genre}")
def validate_json(
    decade: str = FastAPIPath(...),
    genre: str = FastAPIPath(...)
):
    filename = f"{decade}_{genre}_en.json"
    base_dir = Path(__file__).resolve().parent.parent.parent  # ← adjust from /backend/routers/
    full_path = base_dir / "data/json_files/genredecade" / decade / filename

    logger.info(f"🔍 Validating JSON file: {full_path.resolve()}")

    try:
        data = load_json(decade, filename)
        tracks = data.get("ranking_tables", {}).get("track_ranking", [])
        logger.info(f"📄 Loaded {len(tracks)} track(s) for validation.")
    except FileNotFoundError:
        logger.error(f"❌ File not found: {filename}")
        raise HTTPException(404, f"File not found: {filename}")
    except Exception as e:
        logger.exception(f"❌ Error reading file: {filename}")
        raise HTTPException(500, f"Read error for {filename}: {e}")

    missing_required = []

    for i, t in enumerate(tracks):
        missing = [f for f in REQUIRED_FIELDS_TRACK_RANKING if f not in t or t[f] in (None, "")]
        if missing:
            logger.warning(f"⚠️ Track #{i + 1} — '{t.get('track_name', 'Unknown')}' is missing: {missing}")
            missing_required.append({
                "rank": t.get("rank", i + 1),
                "track_name": t.get("track_name", "Unknown"),
                "missing": missing
            })

    total_tracks = len(tracks)
    invalid_tracks = len(missing_required)
    valid_tracks = total_tracks - invalid_tracks

    if invalid_tracks:
        logger.warning(f"❌ Validation failed: {invalid_tracks} track(s) missing required fields.")
    else:
        logger.info("✅ All tracks passed validation.")

    logger.info(f"🧾 Summary: {total_tracks} tracks checked — {valid_tracks} valid, {invalid_tracks} invalid.")

    return {
        "status": "error" if invalid_tracks else "success",
        "total_tracks": total_tracks,
        "valid_tracks": valid_tracks,
        "invalid_tracks": invalid_tracks,
        "errors": missing_required
    }

