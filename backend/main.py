# backend/main.py
import sys
import io
import logging
from pathlib import Path

from fastapi import FastAPI, Query

from backend import config
from backend.logging_setup import setup_logging

# Routers
from backend.routers import router as json_router            # aggregated: generate/validate/insert + specialty
from backend.router_saved_files import router as save_router
from backend.routers.play_json_track_by_rank import router as playback_router
from backend.routers.tts_intro import intro_router
from backend.routers.tts_detail import detail_router
from backend.routers.tts_artist import artist_router
from backend.routers.tts_regenerator import router as tts_regen_router
from backend.routers import supabase_summary
from backend.routers import supabase_loader

from backend.models import DecadeGenre as DG
# ───────────────── sys.path / stdout ─────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ───────────────── logging ─────────────────
setup_logging()
logging.info(f"Starting TopSpot v{config.APP_VERSION} — Updated {config.LAST_UPDATED}")
logger = logging.getLogger(__name__)

# Force our app loggers to INFO and ensure a console handler exists
logging.getLogger().setLevel(logging.INFO)

for name in [
    "backend",
    "backend.routers",
    "backend.routers.insert_specialty_json",
]:
    logging.getLogger(name).setLevel(logging.INFO)

if not logging.getLogger().handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(h)



# ───────────────── FastAPI app ─────────────────
app = FastAPI(
    title="TopSpot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

import inspect, sys
from backend.models import Decade, Genre

sys.stdout.write("\n===== Decade FULL SOURCE =====\n")
sys.stdout.write(inspect.getsource(Decade))
sys.stdout.write("\n===== END SOURCE =====\n")

sys.stdout.write("\n===== Genre FULL SOURCE =====\n")
sys.stdout.write(inspect.getsource(Genre))
sys.stdout.write("\n===== END SOURCE =====\n")

import logging, inspect
from backend.models import Decade, Genre

logger = logging.getLogger(__name__)
logger.info("Decade defined in: %s", inspect.getsourcefile(Decade))
logger.info("Decade module: %s", Decade.__module__)
logger.info("Genre defined in: %s", inspect.getsourcefile(Genre))
logger.info("Genre module: %s", Genre.__module__)



# --- DEBUG: See where DecadeGenre comes from ---
logger.info("DecadeGenre defined in: %s", inspect.getsourcefile(DG))
logger.info("DecadeGenre module: %s", DG.__module__)


print("🔄 main.py loaded (FastAPI starting up)")

def log_step_test():
    names = ["STEP_1", "STEP_1.A", "STEP_1.B", "STEP_1.B.1", "STEP_1.C"]
    for name in names:
        lg = logging.getLogger(name)
        lg.debug(f"{name} — DEBUG test (should NOT appear at INFO level)")
        lg.info(f"{name} — INFO test (should appear at INFO level)")

@app.get("/")
def read_root():
    log_step_test()
    return {"message": "TopSpot is up and running, partner Mr. Ed: Official Curator🐴"}

@app.get("/version", summary="Get TopSpot version info")
def get_version():
    return {"app_version": config.APP_VERSION, "last_updated": config.LAST_UPDATED}

@app.get("/auth/callback")
def auth_callback(code: str = Query(...)):
    logger.info(f"🔁 Received auth callback with code: {code}")
    return {"message": "✅ Auth callback handled"}

# ───────────────── Routers ─────────────────
# Aggregated JSON routes (generate/validate/insert, incl. specialty insert)
app.include_router(json_router)

# Saved files endpoints
app.include_router(save_router)

# Playback endpoints under /json (keeps your existing paths)
app.include_router(playback_router, prefix="/json")

# TTS endpoints
app.include_router(intro_router)
app.include_router(detail_router)
app.include_router(artist_router)
app.include_router(tts_regen_router)

# Supabase helpers
app.include_router(supabase_summary.router)
app.include_router(supabase_loader.router)

# NOTE: Do NOT also include insert_specialty_json directly here;
# it's already included via `json_router` to avoid duplicate routes.
