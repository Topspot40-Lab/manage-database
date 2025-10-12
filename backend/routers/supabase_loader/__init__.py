from fastapi import APIRouter
from . import play_random, load_data  # more will be added later

router = APIRouter(prefix="/supabase", tags=["Supabase"])
router.include_router(play_random.router)
router.include_router(load_data.router)
