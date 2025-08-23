# backend/main.py
import sys
from pathlib import Path
import io

# --- put the path fix FIRST, before any backend.* imports ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# stdout unicode (ok to keep; guard for environments without .buffer if you want)
sys.stdout = io.TextIOWrapper(getattr(sys.stdout, "buffer", sys.stdout), encoding="utf-8")

from fastapi import FastAPI, Query
import logging
from backend import config
from backend.logging_setup import setup_logging

# Routers
from backend.routers.tts_intro import intro_router
from backend.routers.tts_detail import detail_router
from backend.routers.tts_artist import artist_router
from backend.routers import supabase_summary
from backend.routers.play_json_track_by_rank import router as playback_router
from backend.routers.tts_regenerator import router as tts_regen_router
from backend.routers.locales import router as locales_router
from backend.routers import artist_locales
from backend.routers import track_detail_locales
from backend.routers import supabase_loader
from backend.routers import router as json_router
from backend.router_saved_files import router as save_router
from backend.routers.insert_specialty_json import router as specialty_insert_router

# ✅ ensure this matches the actual file location:
from backend.routers.generate_poprock import router as poprock_router
# from backend.routes.generate_poprock import router as poprock_router  # <-- use this instead if file is in routes/

logger = logging.getLogger(__name__)

# Set up logging BEFORE other logic
setup_logging()
logging.info(f"Starting TopSpot v{config.APP_VERSION} — Updated {config.LAST_UPDATED}")

app = FastAPI(
    title="TopSpot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

print("🔄 main.py loaded (FastAPI starting up)")

def log_step_test():
    list(map(lambda name: (logging.getLogger(name).debug(f"{name} — DEBUG test (should NOT appear at INFO level)"),
                           logging.getLogger(name).info(f"{name} — INFO test (should appear at INFO level)")),
             ["STEP_1", "STEP_1.A", "STEP_1.B", "STEP_1.B.1", "STEP_1.C"]))

@app.get("/")
def read_root():
    log_step_test()
    return {"message": "TopSpot is up and running, partner Mr. Ed: Official Curator🐴"}

@app.get("/version", summary="Get TopSpot version info")
def get_version():
    return {"app_version": config.APP_VERSION, "last_updated": config.LAST_UPDATED}

# ❗ actually expose this endpoint
@app.get("/auth/callback")
def auth_callback(code: str = Query(...)):
    logger.info(f"🔁 Received auth callback with code: {code}")
    return {"message": "✅ Auth callback handled"}

# Routers
app.include_router(json_router)
app.include_router(save_router)
app.include_router(playback_router, prefix="/json")
app.include_router(intro_router)
app.include_router(detail_router)
app.include_router(artist_router)
app.include_router(supabase_summary.router)
app.include_router(supabase_loader.router)
app.include_router(tts_regen_router)
app.include_router(specialty_insert_router, prefix="/json/insert")
app.include_router(locales_router)
app.include_router(artist_locales.router)
app.include_router(track_detail_locales.router)
app.include_router(poprock_router)  # <-- new joint generator
