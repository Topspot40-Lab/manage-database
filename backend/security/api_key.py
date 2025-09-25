from __future__ import annotations
import os
from fastapi import Header, HTTPException

API_KEY_ENV = "TOPSPOT_API_KEY"

async def require_key(x_api_key: str | None = Header(None), key: str | None = None):
    need = os.getenv(API_KEY_ENV)
    if not need:
        return  # disabled in dev
    if x_api_key == need or key == need:
        return
    raise HTTPException(status_code=401, detail="Unauthorized")
