# backend/routers/__init__.py
"""
Router package.

We intentionally DO NOT create a top-level APIRouter here to avoid
accidentally double-registering routers in main.py.

Routers should be imported explicitly, e.g.:

    from backend.routers.generate_json import router as generate_json_router
"""

from .generate_json import router as generate_json_router
from .validate_json import router as validate_json_router
from .insert_json import router as insert_json_router

__all__ = [
    "generate_json_router",
    "validate_json_router",
    "insert_json_router",
]
