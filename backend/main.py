# backend/main.py
# import os
import sys
from pathlib import Path
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# 1) Ensure the project root is at the front of sys.path
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ---------------------------------------------------------------------------
# 2) (Optional) Load environment variables – uncomment if you need .env now
# ---------------------------------------------------------------------------
# from dotenv import load_dotenv
# load_dotenv(project_root / ".env")

# ---------------------------------------------------------------------------
# 3) Local imports that depend on the adjusted sys.path
# ---------------------------------------------------------------------------
from backend.database import init_db
from backend.routers import router as json_router          # <-- NEW PACKAGE
from backend.router_saved_files import router as save_router

# ---------------------------------------------------------------------------
# 4) Build the FastAPI app and plug everything in
# ---------------------------------------------------------------------------
app = FastAPI(
    title="TopSpot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

init_db()                      # create tables / run migrations if needed
app.include_router(json_router)  # /generate-json, /validate-json, /insert-json…
app.include_router(save_router)  # whatever endpoints you already had here
