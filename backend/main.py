# backend/main.py
# import os
import sys
from pathlib import Path
from fastapi import FastAPI
import logging

# ---------------------------------------------------------------------------
# 1) Ensure the project root is at the front of sys.path
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.database import init_db
from backend.routers import router as json_router          # <-- NEW PACKAGE
from backend.router_saved_files import router as save_router
logging.basicConfig(
    level=logging.WARNING  ,  # or WARNING in production
    format='%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s:%(lineno)d]: %(message)s',
    force=True # ✅ Makes sure it's always respected
)



# ---------------------------------------------------------------------------
# 4) Build the FastAPI app and plug everything in
# ---------------------------------------------------------------------------
app = FastAPI(
    title="TopSpot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ✅ Add this root route here
@app.get("/")
def read_root():
    return {"message": "TopSpot is up and running, partner Mr. Ed: Official Curator🐴"}


init_db()                      # create tables / run migrations if needed
app.include_router(json_router)  # /generate-json, /validate-json, /insert-json…
app.include_router(save_router)  # whatever endpoints you already had here
