# backend/database.py

from pathlib import Path
from dotenv import load_dotenv
import os
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

# 1) Explicitly point at the .env in this same folder
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    raise RuntimeError(f"No .env file found at {env_path}")
load_dotenv(env_path)

# 2) Now read the URL
DATABASE_URL = os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    raise RuntimeError("POSTGRES_URL is not set in .env")

# 3) Create the engine
engine = create_engine(DATABASE_URL, echo=True)

def init_db() -> None:
    """Create all tables (if they don't exist). Call once at startup."""
    SQLModel.metadata.create_all(engine)

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it afterwards."""
    with Session(engine) as session:
        yield session
