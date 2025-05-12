# backend/database.py

import os
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

# e.g. POSTGRES_URL=postgresql://user:pass@host:5432/dbname in your .env
DATABASE_URL = os.getenv("POSTGRES_URL")
engine = create_engine(DATABASE_URL, echo=True)

def init_db() -> None:
    """
    Create all tables (if they don't exist).
    Call this once at app startup.
    """
    SQLModel.metadata.create_all(engine)

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency to yield a DB session and close it afterwards.
    """
    with Session(engine) as session:
        yield session
