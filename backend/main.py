# backend/main.py
import sys
from pathlib import Path
import io
from backend.routers.tts_intro import intro_router
from backend.routers.tts_detail import detail_router
from backend.routers.tts_artist import artist_router
from backend.routers import supabase_summary
from backend.routers.play_json_track_by_rank import router as playback_router
from fastapi import Query
import logging

from backend import config
from fastapi import FastAPI
from backend.logging_setup import setup_logging
from backend.routers import router as json_router
from backend.router_saved_files import router as save_router
# from backend.routers.tts_track import router as tts_track_router



logger = logging.getLogger(__name__)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# ---------------------------------------------------------------------------
# 1) Ensure the project root is at the front of sys.path
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent  # 👈 go up one more level
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ✅ Now safe to import config


# Set up logging BEFORE other imports or logic
setup_logging()
logging.info(f"Starting TopSpot v{config.APP_VERSION} — Updated {config.LAST_UPDATED}")

# ---------------------------------------------------------------------------
# 2) FastAPI app setup and routing
# ---------------------------------------------------------------------------

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
    return {
        "app_version": config.APP_VERSION,
        "last_updated": config.LAST_UPDATED
    }

def auth_callback(code: str = Query(...)):
    logger.info(f"🔁 Received auth callback with code: {code}")
    return {"message": "✅ Auth callback handled"}

app.include_router(json_router)
app.include_router(save_router)
app.include_router(playback_router, prefix="/json")
# app.include_router(tts_router)
# app.include_router(tts_track_router)

app.include_router(intro_router)
app.include_router(detail_router)
app.include_router(artist_router)
app.include_router(supabase_summary.router)