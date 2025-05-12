import os, sys
from dotenv import load_dotenv

# 1) Add project root to path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 2) Load .env
load_dotenv()

from fastapi import FastAPI
from backend.database import init_db
from backend.router_json_routes import router as json_router
from backend.router_saved_files import router as save_router

app = FastAPI()

# 3) Initialize tables
init_db()

# 4) Include your routers
app.include_router(json_router)
app.include_router(save_router)
