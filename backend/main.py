# backend/main.py
from __future__ import annotations

import sys
import io
import re
import logging
from pathlib import Path
from fastapi import FastAPI, Query, Request
from fastapi.routing import APIRoute

# ─────────────────────────────────────────────
# 📌 Project Bootstrap
# ─────────────────────────────────────────────
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure console supports UTF-8 logs
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    try:
        sys.stdout = io.TextIOWrapper(
            getattr(sys.stdout, "buffer", sys.stdout), encoding="utf-8"
        )
    except Exception:
        pass

# Prevent duplicate logging handlers under reload
LOGGING_INITIALIZED = False


# ─────────────────────────────────────────────
# 🔖 Custom OpenAPI Unique ID Formatting
# ─────────────────────────────────────────────
def custom_generate_unique_id(route: APIRoute) -> str:
    methods = "-".join(sorted(m.lower() for m in (route.methods or [])))
    path = re.sub(r"[{}\/]", "_", route.path_format).strip("_")
    tag = (route.tags[0] if route.tags else "default").lower()
    func = getattr(route.endpoint, "__name__", "handler")
    return f"{tag}__{methods}__{path}__{func}"


# ─────────────────────────────────────────────
# 🚀 FastAPI App Factory
# ─────────────────────────────────────────────
def create_app() -> FastAPI:
    import os
    from dotenv import load_dotenv

    # Load environment variables
    try:
        load_dotenv(project_root / ".env")
    except Exception:
        pass

    # Initialize logging once
    global LOGGING_INITIALIZED
    if not LOGGING_INITIALIZED:
        from backend.logging_setup import setup_logging
        setup_logging()
        LOGGING_INITIALIZED = True

    logger = logging.getLogger(__name__)

    # Show environment debug info if needed
    if os.getenv("LOG_SHOW_ENV", "").lower() in ("1", "true", "yes", "on"):
        logger.debug(
            "ENV check: spotify=%s, xai=%s, supabase=%s",
            "set" if os.getenv("SPOTIFY_CLIENT_ID") else "missing",
            "set" if os.getenv("XAI_API_KEY") else "missing",
            "set" if os.getenv("SUPABASE_URL") else "missing",
        )

    # Load metadata
    from backend.config.app_cfg import APP_VERSION, LAST_UPDATED, validate_app_metadata
    try:
        validate_app_metadata()
    except Exception:
        pass

    # ─────────────────────────────────────────────
    # 📚 Tags for OpenAPI docs
    # ─────────────────────────────────────────────
    TAGS = [
        {"name": "Meta", "description": "Health, version, and meta endpoints."},
        {"name": "JSON & Files", "description": "JSON loaders and saved file access."},
        {"name": "Playback", "description": "Spotify/local playback and control."},
        {"name": "TTS", "description": "Intro, detail, artist narration synthesis."},
        {"name": "Generators", "description": "Build track lists using xAI/Spotify."},
        {"name": "Locales", "description": "Language utilities and MP3s."},
        {"name": "Collections", "description": "Collections: read, generate, play."},
        {"name": "Supabase/DB", "description": "Database diagnostics and summaries."},
        {"name": "Supabase", "description": "DB playback + loaders."},
        {"name": "Upsert/Import", "description": "Import JSON → DB."},
        {"name": "Narration", "description": "Mobile narration player."},
    ]

    # ─────────────────────────────────────────────
    # 🌐 Create FastAPI App
    # ─────────────────────────────────────────────
    app = FastAPI(
        title="TopSpot API",
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=TAGS,
        swagger_ui_parameters={
            "defaultModelsExpandDepth": 0,
            "defaultModelExpandDepth": 0,
            "displayRequestDuration": True,
            "persistAuthorization": True,
            "docExpansion": "none",
        },
        generate_unique_id_function=custom_generate_unique_id,
    )

    # ─────────────────────────────────────────────
    # 🌍 CORS
    # ─────────────────────────────────────────────
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─────────────────────────────────────────────
    # 🏷️ Utility Meta Routes
    # ─────────────────────────────────────────────
    @app.get("/", tags=["Meta"])
    def root():
        return {"message": "TopSpot is up and running, partner Mr. Ed 🐴"}

    @app.get("/health", tags=["Meta"], include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.get("/version", tags=["Meta"])
    def version():
        return {"version": APP_VERSION, "last_updated": LAST_UPDATED}

    @app.get("/__routes", include_in_schema=False)
    def list_routes(request: Request):
        return sorted(r.path for r in request.app.routes)

    # ─────────────────────────────────────────────
    # 📦 ROUTER IMPORTS
    # ─────────────────────────────────────────────
    from backend.routers.spotify_auth import router as spotify_auth_router
    from backend.routers import router as json_router
    from backend.router_saved_files import router as save_router
    from backend.routers.play_json_track_by_rank import router as json_play_router

    from backend.routers.tts_intro import intro_router
    from backend.routers.tts_detail import detail_router
    from backend.routers.tts_artist import artist_router
    from backend.routers.tts_regenerator import router as tts_regen_router

    from backend.routers.generate_poprock import router as poprock_router
    from backend.routers.generate_folk_acoustic import folk_router
    from backend.routers.enrich_tv_themes import router as enrich_tv_router
    from backend.routers.expand_tv_themes import router as expand_tv_router

    from backend.routers import locales as locales_router
    from backend.routers import artist_locales, track_detail_locales, intros_locales

    from backend.routers.collections import router as collections_router
    from backend.routers.collections_read import router as collections_read_router
    from backend.routers.collections_generate import router as collections_generate_router
    from backend.routers.collections_player import router as collections_player_router
    from backend.routers.tts_collection_intro import collection_intro_router

    from backend.routers import supabase_summary, supabase_loader
    from backend.routers.upsert_json import router as upsert_router

    from backend.routers.ads_scripts import router as ads_router
    from backend.routers.meta_logging import router as meta_logging_router

    from backend.routers.narration import router as narration_router

    from backend.routers import catalog
    from backend.routers.decade_genre_player import router as decade_genre_router
    from backend.routers import playback_control

    # ─────────────────────────────────────────────
    # 📎 REGISTER ROUTERS
    # ─────────────────────────────────────────────
    app.include_router(json_router, tags=["JSON & Files"])
    app.include_router(save_router, tags=["JSON & Files"])
    app.include_router(json_play_router, tags=["Playback"])

    # TTS
    app.include_router(intro_router, tags=["TTS"])
    app.include_router(detail_router, tags=["TTS"])
    app.include_router(artist_router, tags=["TTS"])
    app.include_router(tts_regen_router, tags=["TTS"])

    # Generators
    app.include_router(poprock_router, tags=["Generators"])
    app.include_router(folk_router, tags=["Generators"])
    app.include_router(enrich_tv_router, tags=["Generators"])
    app.include_router(expand_tv_router, tags=["Generators"])

    # Locales
    app.include_router(locales_router.router, tags=["Locales"])
    app.include_router(artist_locales.router, tags=["Locales"])
    app.include_router(track_detail_locales.router, tags=["Locales"])
    app.include_router(intros_locales.router, tags=["Locales"])

    # Collections
    app.include_router(collections_router, tags=["Collections"])
    app.include_router(collections_read_router, tags=["Collections"])
    app.include_router(collections_generate_router, tags=["Collections"])
    app.include_router(collections_player_router)
    app.include_router(collection_intro_router)

    # Supabase
    app.include_router(supabase_summary.router, tags=["Supabase/DB"])
    app.include_router(supabase_loader.router, tags=["Supabase"])

    # Import / Upsert
    app.include_router(upsert_router, tags=["Upsert/Import"])

    # Meta
    app.include_router(ads_router, tags=["Meta"])
    app.include_router(meta_logging_router, tags=["Meta"])

    # Narration
    app.include_router(narration_router, tags=["Narration"])

    # Catalog + Decade/Genre
    app.include_router(catalog.router)
    app.include_router(decade_genre_router)

    # Playback Control
    app.include_router(playback_control.router, tags=["Playback"])

    # Spotify Auth
    app.include_router(spotify_auth_router, tags=["Meta"])

    # ─────────────────────────────────────────────
    # 🧹 Tag Validation at Startup
    # ─────────────────────────────────────────────
    ALLOWED = {x["name"] for x in TAGS}

    @app.on_event("startup")
    async def verify_tags():
        seen = {tag for r in app.routes if isinstance(r, APIRoute) for tag in (r.tags or [])}
        unknown = sorted(seen - ALLOWED)
        if unknown:
            logging.getLogger("backend.tags").warning(
                "⚠️ Unknown/stray tags in routes: %s", ", ".join(unknown)
            )

    @app.on_event("startup")
    async def startup_banner():
        logging.getLogger("backend.startup").info(
            "✅ Startup complete; routes registered: %d",
            len(app.routes)
        )

    return app


# ─────────────────────────────────────────────
# 📌 Export App for Uvicorn
# ─────────────────────────────────────────────
app = create_app()
