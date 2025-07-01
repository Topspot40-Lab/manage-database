# backend/main.py
import sys
from pathlib import Path
import io


# print("This will disappear in 3 seconds...")
# import os
# import time
# time.sleep(3)
# os.system('cls')
# print("Screen cleared!")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# ---------------------------------------------------------------------------
# 1) Ensure the project root is at the front of sys.path
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent  # 👈 go up one more level
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ✅ Now safe to import config
from backend import config

from fastapi import FastAPI
import logging
from backend.logging_setup import setup_logging

# Set up logging BEFORE other imports or logic
setup_logging()
logging.info(f"Starting TopSpot v{config.APP_VERSION} — Updated {config.LAST_UPDATED}")

# ---------------------------------------------------------------------------
# 2) FastAPI app setup and routing
# ---------------------------------------------------------------------------
from backend.routers import router as json_router
from backend.router_saved_files import router as save_router

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


app.include_router(json_router)
app.include_router(save_router)
