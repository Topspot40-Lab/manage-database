from fastapi import APIRouter, Query
from pathlib import Path
from backend.services.track_cache import get_all_rankings
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_INTRO

router = APIRouter()

@router.post("/tts/generate-intro-tts-by-rank")
def generate_intro_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1)
):
    if start_rank > end_rank:
        return {"error": "Start rank must be <= end rank"}

    rankings = get_all_rankings()
    output_dir = Path("data/mp3_files/intro_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files = []

    for entry in rankings:
        rank = entry.get("rank")
        if rank is None or not (start_rank <= rank <= end_rank):
            continue

        intro_text = entry.get("intro")
        decade = entry.get("decade", "unknown").replace(" ", "_").lower()
        genre = entry.get("genre", "unknown").replace(" ", "_").lower()

        if not intro_text:
            continue

        filename = f"{decade}_{genre}_{rank:02d}.mp3"
        out_path = output_dir / filename

        generate_tts_mp3(intro_text, out_path, VOICE_ID_INTRO, overwrite=True)
        generated_files.append(str(out_path))

    return {
        "message": f"✅ Generated {len(generated_files)} intro TTS files",
        "files": generated_files
    }
