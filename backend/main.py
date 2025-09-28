# backend/main.py
from __future__ import annotations

import sys
import io
import re
from pathlib import Path
from fastapi import FastAPI, Query, Request
from fastapi.routing import APIRoute

# ── Project path bootstrap (safe for uvicorn --reload) ─────────────
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ── Stdout UTF-8 (prefer reconfigure; fall back if missing) ─────────
try:
    sys.stdout.reconfigure(encoding="utf-8")  # py3.7+
except Exception:
    try:
        sys.stdout = io.TextIOWrapper(getattr(sys.stdout, "buffer", sys.stdout), encoding="utf-8")
    except Exception:
        pass


def custom_generate_unique_id(route: APIRoute) -> str:
    """Include method(s), path, tag, and function name for readability/uniqueness."""
    methods = "-".join(sorted(m.lower() for m in (route.methods or [])))
    path = re.sub(r"[{}\/]", "_", route.path_format).strip("_")
    tag = (route.tags[0] if route.tags else "default").lower()
    func = getattr(route.endpoint, "__name__", "handler")
    return f"{tag}__{methods}__{path}__{func}"


def create_app() -> FastAPI:
    """Factory to build the FastAPI app (keeps import-time side effects out)."""
    import os
    import logging

    # ── Env + logging (inside factory) ──────────────────────────────
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=project_root / ".env")
    except Exception:
        pass

    from backend.logging_setup import setup_logging
    setup_logging()
    logger = logging.getLogger(__name__)

    SHOW_ENV = os.getenv("LOG_SHOW_ENV", "").lower() in ("1", "true", "yes", "on")
    if logger.isEnabledFor(logging.DEBUG) or SHOW_ENV:
        sp_id = os.getenv("SPOTIPY_CLIENT_ID") or os.getenv("SPOTIFY_CLIENT_ID")
        logger.debug(
            "ENV check: spoti(client_id)=%s, xai=%s, supabase_url=%s",
            "set" if sp_id else "missing",
            "set" if os.getenv("XAI_API_KEY") else "missing",
            "set" if os.getenv("SUPABASE_URL") else "missing",
        )

    # ── App metadata (tolerant if module missing) ───────────────────
    APP_VERSION, LAST_UPDATED = "dev", "n/a"
    try:
        from backend.config.app_cfg import (
            APP_VERSION as _V,
            LAST_UPDATED as _LU,
            validate_app_metadata,
        )
        APP_VERSION, LAST_UPDATED = _V, _LU
        validate_app_metadata()
    except Exception:
        pass

    # ── API app + docs metadata ─────────────────────────────────────
    TAGS_METADATA = [
        {"name": "Meta",           "description": "Health, version, and misc app metadata."},
        {"name": "JSON & Files",   "description": "Read/write JSON and saved-file helpers."},
        {"name": "Playback",       "description": "Play tracks from JSON/DB (Spotify/local)."},
        {"name": "TTS",            "description": "Intro/Detail/Artist speech synthesis & regen."},
        {"name": "Generators",     "description": "Build/enrich data (xAI, Spotify, TV Themes)."},
        {"name": "Locales",        "description": "ES/PT-BR texts and MP3 generation utilities."},
        {"name": "Collections",    "description": "Collections import/read/generate pipelines."},
        {"name": "Supabase/DB",    "description": "DB summaries, loaders, diagnostics."},
        {"name": "Supabase",       "description": "DB-backed playback and loaders."},  # ← added
        {"name": "Upsert/Import",  "description": "Import & upsert JSON track data into DB."},
        {"name": "Narration",      "description": "Mobile narration player & signed URLs."},
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
            # "docExpansion": "list",   # set to "none" to collapse sections by default
            "docExpansion": "none",   # set to "none" to collapse sections by default
        },
        generate_unique_id_function=custom_generate_unique_id,
    )

    # Startup breadcrumb (level controlled by LOG_SHOW_STARTUP)
    _startup_log = logging.getLogger("backend.startup")
    if os.getenv("LOG_SHOW_STARTUP", "").lower() in ("1", "true", "yes", "on"):
        _startup_log.info("🔄 main.py loaded (FastAPI starting up)")
    else:
        _startup_log.debug("🔄 main.py loaded (FastAPI starting up)")

    # ── Meta + utilities (inline endpoints) ─────────────────────────
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

    # ── Router imports inside factory (avoid early side effects) ────
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

    # Mobile narration (new, modularized)
    from backend.routers.narration import router as narration_router

    from backend.routers.collections_player import router as collections_player_router

    # ── Include routers (tags defined ONLY here) ────────────────────
    # 1) Core JSON / Files / Playback / TTS
    app.include_router(json_router,         tags=["JSON & Files"])
    app.include_router(save_router,         tags=["JSON & Files"])
    app.include_router(playback_router,     tags=["Playback"])
    app.include_router(intro_router,        tags=["TTS"])
    app.include_router(detail_router,       tags=["TTS"])
    app.include_router(artist_router,       tags=["TTS"])
    app.include_router(tts_regen_router,    tags=["TTS"])

    # 2) Generators / Enrichers
    app.include_router(poprock_router,      tags=["Generators"])
    app.include_router(folk_router,         tags=["Generators"])
    app.include_router(enrich_tv_router,    tags=["Generators"])
    app.include_router(expand_tv_router,    tags=["Generators"])

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
    app.include_router(supabase_summary.router, tags=["Supabase/DB"])  # diagnostics
    app.include_router(supabase_loader.router,  tags=["Supabase"])     # playback/loaders

    # 6) Upsert / Import
    app.include_router(upsert_router, tags=["Upsert/Import"])

    # 7) Ads + Meta diagnostics
    app.include_router(ads_router,          tags=["Meta"])
    app.include_router(meta_logging_router, tags=["Meta"])

    # 8) Mobile narration (MP3-on-phone flow)
    app.include_router(narration_router, tags=["Narration"])

    app.include_router(collections_player_router)

    # ── Normalize tags so each route has exactly ONE canonical tag ──
    CANON_BY_PREFIX = [
        ("/tts",               "TTS"),
        ("/playback",          "Playback"),
        ("/json",              "JSON & Files"),
        ("/files",             "JSON & Files"),
        ("/gen",               "Generators"),
        ("/locales",           "Locales"),
        ("/collections",       "Collections"),
        ("/supabase/summary",  "Supabase/DB"),
        ("/supabase",          "Supabase"),
        ("/upsert",            "Upsert/Import"),
        ("/narration",         "Narration"),
        ("/meta",              "Meta"),
        ("/ads",               "Meta"),
        ("/version",           "Meta"),
        ("/health",            "Meta"),
        ("/",                  None),  # let root keep its explicit tag
    ]
    ALLOWED = {t["name"] for t in TAGS_METADATA}

    def _canonical_for(path: str) -> str | None:
        for prefix, tag in CANON_BY_PREFIX:
            if prefix and path.startswith(prefix):
                return tag
        return None

    # Do the rewrite BEFORE docs are first rendered
    from fastapi.routing import APIRoute as _APIRoute
    for r in list(app.routes):
        if isinstance(r, _APIRoute):
            desired = _canonical_for(r.path)
            if desired:
                r.tags[:] = [desired]  # enforce single canonical tag

    # Warn on any stray/unknown tags (helps keep things tidy)
    @app.on_event("startup")
    async def _verify_tags():
        warn = logging.getLogger("backend.tags")
        seen = set()
        for r in app.routes:
            if isinstance(r, APIRoute):
                for t in (r.tags or []):
                    seen.add(t)
        unknown = sorted(seen - ALLOWED)
        if unknown:
            warn.warning("⚠️ Unknown/stray tags in routes: %s", ", ".join(unknown))

    @app.on_event("startup")
    async def _startup_banner():
        logging.getLogger("backend.startup").info(
            "✅ Startup complete; routes registered: %d", len(app.routes)
        )

    return app


# Optional export for uvicorn:  uvicorn backend.main:app
app = create_app()
