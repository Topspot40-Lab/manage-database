# backend/routers/meta_logging.py
from __future__ import annotations
import logging
from fastapi import APIRouter

router = APIRouter(prefix="/meta", tags=["Meta"])

log = logging.getLogger("backend.meta.log_demo")

@router.get("/log-demo", summary="Emit logs at all levels")
def log_demo():
    log.debug("🧪 DEBUG: log-demo hit (debug)")
    log.info("🧪 INFO: log-demo hit (info)")
    log.warning("🧪 WARNING: log-demo hit (warning)")
    log.error("🧪 ERROR: log-demo hit (error)")
    log.critical("🧪 CRITICAL: log-demo hit (critical)")
    return {"ok": True, "message": "Emitted logs at all levels; check console/file."}
