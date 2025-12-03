# backend/main.py
from __future__ import annotations

import os
import logging
from pathlib import Path
from importlib import import_module
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

# Load .env
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except Exception:
    pass

# Logging
from backend.logging_setup import setup_logging
setup_logging()

logger = logging.getLogger("backend.startup")

BASE_DIR = Path(__file__).resolve().parent
ROUTER_DIR = BASE_DIR / "routers"


# ─────────────────────────────────────────────
# FLEXIBLE ROUTER DISCOVERY
# ─────────────────────────────────────────────
def load_all_routers(app: FastAPI):
    """
    Load ANY APIRouter object found in router modules.
    This catches:
        - router
        - x_router
        - router_x
        - api_router
        - supabase_router
        - tts_router
        - routes
        - ANY unnamed APIRouter instance
    """

    for file in ROUTER_DIR.glob("*.py"):
        if file.name.startswith("__"):
            continue

        module_name = f"backend.routers.{file.stem}"

        try:
            module = import_module(module_name)
        except Exception as e:
            logger.error(f"❌ Failed importing {module_name}: {e}")
            continue

        found = []

        # Inspect all attributes in module
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, APIRouter):
                found.append((attr_name, obj))

        if not found:
            logger.debug(f"⏭ No APIRouter found in {file.name}")
            continue

        # Mount all routers (usually 1)
        for attr_name, router_obj in found:
            try:
                app.include_router(router_obj)
                logger.info(
                    f"🔌 Mounted {file.name:<25} "
                    f"router={attr_name:<15} "
                    f"prefix={router_obj.prefix:<20} "
                    f"tags={router_obj.tags}"
                )

            except Exception as e:
                logger.error(f"❌ Failed mounting router in {file.name}: {e}")


# ─────────────────────────────────────────────
# APP FACTORY
# ─────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="TopSpot JSON Creator",
        version=os.getenv("APP_VERSION", "dev"),
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Load routers
    load_all_routers(app)

    @app.on_event("startup")
    async def _startup():
        logger.info("🔄 FastAPI starting… main.py loaded")

    return app


# ASGI app
app = create_app()
