# backend/main.py
from __future__ import annotations

import sys
import io
from pathlib import Path
from fastapi import FastAPI, Query, Request

# ── Minimal top-level only: path + stdout (safe for reloader) ─────────────
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure stdout handles UTF-8 (emojis, etc.)
sys.stdout = io.TextIOWrapper(getattr(sys.stdout, "buffer", sys.stdout), encoding="utf-8")


def create_app() -> FastAPI:
    """
    Factory to build the FastAPI app.
    Keeps side-effects out of import time so uvicorn --reload is safe.
    """
    import os
    import logging

    # ── Load env + logging *inside* factory (avoids double wiring) ────────
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=project_root / ".env")
    except Exception:
        pass

    from backend.logging_setup import setup_logging
    setup_logging()  # should be idempotent; if not, add a guard there

    logger = logging.getLogger(__name__)

    SHOW_ENV = os.getenv("LOG_SHOW_ENV", "").lower() in ("1", "true", "yes", "on")
    if logger.isEnabledFor(logging.DEBUG) or SHOW_ENV:
        logger.debug(
            "ENV check: spotify=%s, xai=%s, supabase_url=%s",
            "set" if os.getenv("SPOTIFY_CLIENT_ID") else "missing",
            "set" if os.getenv("XAI_API_KEY") else "missing",
            "set" if os.getenv("SUPABASE_URL") else "missing",
        )

    # ── App metadata (tolerant if config module missing) ──────────────────
    APP_VERSION, LAST_UPDATED = "dev", "n/a"
    try:
        from backend.config.app_cfg import APP_VERSION as _V, LAST_UPDATED as _LU, validate_app_metadata
        APP_VERSION, LAST_UPDATED = _V, _LU
        validate_app_metadata()
    except Exception:
        pass

    # ── API app + docs metadata ───────────────────────────────────────────
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
        version=APP_VERSION,
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
    )

    # Startup breadcrumb (mute with LOG_SHOW_STARTUP=false)
    _startup_log = logging.getLogger("backend.startup")
    if os.getenv("LOG_SHOW_STARTUP", "").lower() in ("1", "true", "yes", "on"):
        _startup_log.info("🔄 main.py loaded (FastAPI starting up)")
    else:
        _startup_log.debug("🔄 main.py loaded (FastAPI starting up)")

    # ── Meta + utilities (inline endpoints) ───────────────────────────────
    @app.get("/__routes", include_in_schema=False)
    def __routes(request: Request):
        return sorted(getattr(r, "path", getattr(r, "path_format", "?")) for r in request.app.routes)

    @app.get("/", tags=["Meta"])
    def read_root():
        return {"message": "TopSpot is up and running, partner Mr. Ed: Official Curator 🐴"}

    @app.get("/health", tags=["Meta"], include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.get("/version", summary="Get TopSpot version info", tags=["Meta"])
    def get_version():
        return {"app_version": APP_VERSION, "last_updated": LAST_UPDATED}

    @app.get("/auth/callback", tags=["Meta"])
    def auth_callback(code: str = Query(...)):
        logger.info("🔁 Received auth callback with code: %s", code)
        return {"message": "✅ Auth callback handled"}

    # ── Router imports *inside* factory (prevents early import side-effects)
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

    # Supabase / DB Utilities
    from backend.routers import supabase_summary, supabase_loader

    # Upsert / Import
    from backend.routers.upsert_json import router as upsert_router

    # Ads + Meta diagnostics
    from backend.routers.ads_scripts import router as ads_router
    from backend.routers.meta_logging import router as meta_logging_router

    # ── Include routers (grouped) ─────────────────────────────────────────
    # 1) Core JSON / Files / Playback / TTS
    app.include_router(json_router, tags=["JSON & Files"])
    app.include_router(save_router, tags=["JSON & Files"])
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
    app.include_router(supabase_summary.router, tags=["Supabase/DB"])
    app.include_router(supabase_loader.router,  tags=["Supabase/DB"])

    # 6) Upsert / Import
    app.include_router(upsert_router, tags=["Upsert/Import"])

    # 7) Ads + Meta diagnostics
    app.include_router(ads_router)
    app.include_router(meta_logging_router, tags=["Meta"])

    # Final startup ping
    @app.on_event("startup")
    async def _startup_banner():
        logging.getLogger("backend.startup").info(
            "✅ Startup complete; routes registered: %d", len(app.routes)
        )

    return app

app = create_app()  # optional export for uvicorn backend.main:app
