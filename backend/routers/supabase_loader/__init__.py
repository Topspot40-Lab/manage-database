from fastapi import APIRouter
from . import play_random, load_data, list_collections  # 👈 add this

router = APIRouter(prefix="/supabase", tags=["Supabase"])
router.include_router(play_random.router)
router.include_router(load_data.router)
router.include_router(list_collections.router)  # 👈 add this line
