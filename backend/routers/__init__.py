from fastapi import APIRouter
from .generate_json import router as gen_router
from .validate_json import router as val_router
from .insert_json import router as ins_router

router = APIRouter()
router.include_router(gen_router)
router.include_router(val_router)
router.include_router(ins_router)
