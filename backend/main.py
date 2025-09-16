# backend/main.py
from __future__ import annotations

import sys
import io
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# --- put the path fix FIRST, before any backend.* imports ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ensure stdout handles UTF-8 (emojis etc.)
sys.stdout = io.TextIOWrapper(getattr(sys.stdout, "buffer", sys.stdout), encoding="utf-8")

from fastapi import FastAPI, Query

from backend import config
from backend.logging_setup import setup_logging

# ------------------------ Lifespan (startup/shutdown) ------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- runs at startup ---
    log = logging.getLogger(__name__)
    for r in app.routes:
        try:
            methods = ",".join(sorted(getattr(r, "methods", [])))
        except Exception:
            methods = ""
        log.info("Route: %s  Methods: %s", getattr(r, "path", "?"), methods)
    yield
    # --- runs at shutdown ---
    # (nothing to do here)

# ------------------------ Routers ------------------------

# TTS
from backend.routers.tts_intro import intro_router
from backend.routers.tts_detail import detail_router
from backend.routers.tts_artist import artist_router
from backend.routers.tts_regenerator import router as tts_regen_router

# JSON / Files / Playback
from backend.routers import router as json_router
from backend.router_saved_files import router as save_router
from backend.routers.play_json_track_by_rank import router as playback_router

# Generators / Enrichers
from backend.routers.generate_poprock import router as poprock_router
from backend.routers.generate_folk_acoustic import folk_router
from backend.routers.enrich_tv_themes import router as enrich_tv_router
from backend.routers.expand_tv_themes import router as expand_tv_router

# Collections
from backend.routers.collections import router as collections_router
from backend.routers.collections_read import router as collections_read_router
from backend.routers.collections_generate import router as collections_generate_router

# Locales
from backend.routers import locales as locales_router
from backend.routers import artist_locales
from backend.routers import track_detail_locales
from backend.routers import intros_locales

# NEW: reorganized upsert/import endpoints
from backend.routers.upsert_json import router as upsert_router

logger = logging.getLogger(__name__)

# Set up logging BEFORE other logic
setup_logging()
logger.info("Starting TopSpot v%s — Updated %s", config.APP_VERSION, config.LAST_UPDATED)

# ------------------------ Docs / Tag Metadata ------------------------
TAGS_METADATA = [
    {"name": "Meta",           "description": "Health, version, and misc app metadata."},
    {"name": "JSON & Files",   "description": "Read/write JSON and saved-file helpers."},
    {"name": "Playback",       "description": "Play tracks from JSON/DB (Spotify/local)."},
    {"name": "TTS",            "description": "Intro/Detail/Artist speech synthesis & regen."},
    {"name": "Generators",     "description": "Build/enrich data (xAI, Spotify, TV Themes)."},
    {"name": "Locales",        "description": "ES/PT-BR texts and MP3 generation utilities."},
    {"name": "Collections",    "description": "Collections import/read/generate pipelines."},
    {"name": "Supabase/DB",    "description": "DB summaries, loaders, diagnostics."},
    {"name": "Upsert/Import",  "description": "Import & upsert JSON track data into DB."},
]

app = FastAPI(
    title="TopSpot API",
    version=config.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=TAGS_METADATA,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 0,
        "defaultModelExpandDepth": 0,
        "displayRequestDuration": True,
        "persistAuthorization": True,
        "docExpansion": "list",
    },
    lifespan=lifespan,   # ✅ use lifespan, not @on_event
)

print("🔄 main.py loaded (FastAPI starting up)")

# ------------------------ Meta ------------------------
@app.get("/", tags=["Meta"])
def read_root():
    return {"message": "TopSpot is up and running, partner Mr. Ed: Official Curator 🐴"}

@app.get("/health", tags=["Meta"], include_in_schema=False)
def health():
    return {"status": "ok"}

@app.get("/version", summary="Get TopSpot version info", tags=["Meta"])
def get_version():
    return {"app_version": config.APP_VERSION, "last_updated": config.LAST_UPDATED}

@app.get("/auth/callback", tags=["Meta"])
def auth_callback(code: str = Query(...)):
    logger.info("🔁 Received auth callback with code: %s", code)
    return {"message": "✅ Auth callback handled"}

# ------------------------ Include Routers (organized + tagged) ------------------------
# 1) Core JSON / Files / Playback / TTS
app.include_router(json_router, tags=["JSON & Files"])
app.include_router(save_router, tags=["JSON & Files"])

# Playback — choose ONE variant to avoid double "/json"
app.include_router(playback_router, tags=["Playback"])

app.include_router(intro_router,     tags=["TTS"])
app.include_router(detail_router,    tags=["TTS"])
app.include_router(artist_router,    tags=["TTS"])
app.include_router(tts_regen_router, tags=["TTS"])

# 2) Generators / Enrichers
app.include_router(poprock_router,   tags=["Generators"])
app.include_router(folk_router,      tags=["Generators"])
app.include_router(enrich_tv_router, tags=["Generators"])
app.include_router(expand_tv_router, tags=["Generators"])

# 3) Locales
app.include_router(locales_router.router,       tags=["Locales"])
app.include_router(artist_locales.router,       tags=["Locales"])
app.include_router(track_detail_locales.router, tags=["Locales"])
app.include_router(intros_locales.router,       tags=["Locales"])

# 4) Collections
app.include_router(collections_router,          tags=["Collections"])
app.include_router(collections_read_router,     tags=["Collections"])
app.include_router(collections_generate_router, tags=["Collections"])

# 5) Supabase / DB Utilities
from backend.routers import supabase_summary, supabase_loader
app.include_router(supabase_summary.router, tags=["Supabase/DB"])
app.include_router(supabase_loader.router,  tags=["Supabase/DB"])

# 6) Upsert / Import (new package)
app.include_router(upsert_router, tags=["Upsert/Import"])

# 🚫 removed deprecated @app.on_event("startup") handler
