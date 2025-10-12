from fastapi import APIRouter
from backend.state import current_decade_genre, current_collection

router = APIRouter(tags=["Supabase: Context"])

@router.get("/current-context")
def get_current_context():
    mode = "collection" if current_collection.get("collection") else (
        "decade_genre" if current_decade_genre.get("decade") and current_decade_genre.get("genre") else None
    )
    return {
        "mode": mode,
        "decade_genre": current_decade_genre,
        "collection": current_collection,
    }
