# backend/main.py
import sys
from pathlib import Path
import io
import logging

# --- put the path fix FIRST, before any backend.* imports ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# stdout unicode (ok to keep; guard for environments without .buffer if you want)
sys.stdout = io.TextIOWrapper(getattr(sys.stdout, "buffer", sys.stdout), encoding="utf-8")

from fastapi import FastAPI, Query

from backend import config
from backend.logging_setup import setup_logging

# Routers (specific)
from backend.routers.tts_intro import intro_router
from backend.routers.tts_detail import detail_router
from backend.routers.tts_artist import artist_router
from backend.routers.play_json_track_by_rank import router as playback_router
from backend.routers.tts_regenerator import router as tts_regen_router
from backend.routers import router as json_router
from backend.router_saved_files import router as save_router
from backend.routers.generate_poprock import router as poprock_router
from backend.routers.generate_folk_acoustic import folk_router   # ← NEW
from backend.routers.enrich_tv_themes import router as enrich_tv_router  # ← NEW
from backend.routers.expand_tv_themes import router as expand_tv_router
from backend.routers.collections import router as collections_router
from backend.routers.collections_read import router as collections_read_router
from backend.routers.collections_generate import router as collections_generate_router



# Routers (modules we include with .router)
from backend.routers import (
    supabase_summary,
    supabase_loader,
    locales as locales_router,
    artist_locales,
    track_detail_locales,
    intros_locales,   # ← NEW
)

logger = logging.getLogger(__name__)

# Set up logging BEFORE other logic
setup_logging()
logging.info(f"Starting TopSpot v{config.APP_VERSION} — Updated {config.LAST_UPDATED}")

# ------------------------ Docs / Tag Metadata ------------------------
TAGS_METADATA = [
    {"name": "Meta",           "description": "Health, version, and misc app metadata."},
    {"name": "JSON & Files",   "description": "Read/write JSON and saved-file helpers."},
    {"name": "Playback",       "description": "Play tracks from JSON/DB (Spotify/local)."},
    {"name": "TTS",            "description": "Intro/Detail/Artist speech synthesis & regen."},
    {"name": "Generators",     "description": "Build/enrich data (XAI, Spotify, TV Themes)."},
    {"name": "Locales",        "description": "ES/PT-BR texts and MP3 generation utilities."},
    {"name": "Collections",    "description": "Collections import/read/generate pipelines."},
    {"name": "Supabase/DB",    "description": "DB summaries, loaders, diagnostics."},
]

app = FastAPI(
    title="TopSpot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=TAGS_METADATA,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 0,  # hide the Models panel
        "defaultModelExpandDepth": 0,    # collapse schemas on each endpoint
        "displayRequestDuration": True,  # show request timings
        "persistAuthorization": True,    # keep auth between reloads
        "docExpansion": "list",          # show tag list; endpoints collapsed
    },
)

print("🔄 main.py loaded (FastAPI starting up)")

def log_step_test():
    list(map(lambda name: (logging.getLogger(name).debug(f"{name} — DEBUG test (should NOT appear at INFO level)"),
                           logging.getLogger(name).info(f"{name} — INFO test (should appear at INFO level)")),
             ["STEP_1", "STEP_1.A", "STEP_1.B", "STEP_1.B.1", "STEP_1.C"]))
@app.get("/", tags=["Meta"])
def read_root():
    log_step_test()
    return {"message": "TopSpot is up and running, partner Mr. Ed: Official Curator🐴"}

@app.get("/health", tags=["Meta"], include_in_schema=False)

def health():
    return {"status": "ok"}

@app.get("/version", summary="Get TopSpot version info", tags=["Meta"])
def get_version():
    return {"app_version": config.APP_VERSION, "last_updated": config.LAST_UPDATED}

@app.get("/auth/callback", tags=["Meta"])
def auth_callback(code: str = Query(...)):
    logger.info(f"🔁 Received auth callback with code: {code}")
    return {"message": "✅ Auth callback handled"}


# ------------------------ Include Routers (organized + tagged) ------------------------
# 1) Core JSON / Files / Playback / TTS
app.include_router(json_router, tags=["JSON & Files"])
app.include_router(save_router, tags=["JSON & Files"])

# Playback — choose ONE variant to avoid double "/json"
# (Use this if the router already defines prefix="/json" internally)
app.include_router(playback_router, tags=["Playback"])
# (Else) app.include_router(playback_router, prefix="/json", tags=["Playback"])

app.include_router(intro_router,     tags=["TTS"])
app.include_router(detail_router,    tags=["TTS"])
app.include_router(artist_router,    tags=["TTS"])
app.include_router(tts_regen_router, tags=["TTS"])

# 2) Generators / Enrichers
app.include_router(poprock_router,   tags=["Generators"])
app.include_router(folk_router,      tags=["Generators"])      # /generate/folk-acoustic/build
app.include_router(enrich_tv_router, tags=["Generators"])      # /enrich/tv-themes/{decade}
app.include_router(expand_tv_router, tags=["Generators"])      # /expand/tv-themes/...

# 3) Locales (routers already have /locales prefixes; don't add include-time prefix)
app.include_router(locales_router.router,       tags=["Locales"])
app.include_router(artist_locales.router,       tags=["Locales"])
app.include_router(track_detail_locales.router, tags=["Locales"])
app.include_router(intros_locales.router,       tags=["Locales"])

# 4) Collections
app.include_router(collections_router,          tags=["Collections"])
app.include_router(collections_read_router,     tags=["Collections"])
app.include_router(collections_generate_router, tags=["Collections"])

# 5) Supabase / DB Utilities
app.include_router(supabase_summary.router, tags=["Supabase/DB"])
app.include_router(supabase_loader.router,  tags=["Supabase/DB"])
