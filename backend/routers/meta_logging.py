# backend/routers/meta_logging.py
from __future__ import annotations
import logging
from typing import List, Optional, Dict
from fastapi import APIRouter, Query

# Read your single source of truth
import backend.config.logging_vars as lv

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


@router.get("/loggers", summary="Show effective levels for selected loggers")
def list_loggers(
    names: Optional[List[str]] = Query(
        default=None,
        description="Logger names to inspect. If omitted, a useful default set is used."
    )
) -> Dict[str, str]:
    default_names = [
        "backend.startup",
        "backend.meta.log_demo",
        "backend.routers.supabase_loader",
        "backend.routers.collections",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "spotipy",
        "urllib3",
        "requests",
        "httpx",
    ]
    check = names or default_names
    return {
        n: logging.getLevelName(logging.getLogger(n).getEffectiveLevel())
        for n in check
    }


@router.get("/loggers/all", summary="List all instantiated loggers and their effective levels")
def list_all_instantiated_loggers() -> Dict[str, str]:
    # Only loggers that have been created (imported/used) appear here
    out: Dict[str, str] = {}
    for name, lg in logging.Logger.manager.loggerDict.items():
        if isinstance(lg, logging.Logger):
            out[name] = logging.getLevelName(lg.getEffectiveLevel())
    # Sorted for stable output
    return dict(sorted(out.items()))


@router.get("/loggers/debug", summary="Show which modules are at DEBUG")
def list_debug_modules():
    # Configured DEBUG (from logging_vars.py – intent)
    configured_debug = sorted(
        [name for name, lvl in (lv.LOG_LEVELS_BY_MODULE or {}).items()
         if str(lvl).upper() == "DEBUG"]
    )
    # Effective DEBUG (only instantiated loggers right now)
    effective_debug = sorted(
        [
            name for name, lg in logging.Logger.manager.loggerDict.items()
            if isinstance(lg, logging.Logger) and lg.getEffectiveLevel() == logging.DEBUG
        ]
    )
    # Diffs to help debugging configuration vs reality
    configured_but_not_instantiated = sorted(set(configured_debug) - set(effective_debug))
    unexpected_debug_instantiated = sorted(
        set(effective_debug) - set(configured_debug)
    )

    root_level = logging.getLevelName(logging.getLogger().getEffectiveLevel())
    return {
        "root_level": root_level,
        "configured_debug": configured_debug,
        "effective_debug_instantiated": effective_debug,
        "configured_but_not_instantiated": configured_but_not_instantiated,
        "unexpected_debug_instantiated": unexpected_debug_instantiated,
        "note": "Configured comes from logging_vars.py; Effective shows loggers currently created and inheriting levels at runtime.",
    }


@router.get("/loggers/config", summary="Show logging configuration values")
def logging_config_snapshot():
    # A concise snapshot of the core knobs you control
    return {
        "root.LOG_LEVEL": getattr(lv, "LOG_LEVEL", None),
        "LOG_SHOW_CONFIG": getattr(lv, "LOG_SHOW_CONFIG", None),
        "modules_count": len(getattr(lv, "LOG_LEVELS_BY_MODULE", {})),
        "modules": lv.LOG_LEVELS_BY_MODULE,  # full mapping for quick inspection
    }


@router.get("/loggers/effective", summary="Effective levels for all names in LOG_LEVELS_BY_MODULE")
def effective_for_configured_modules():
    names = list((lv.LOG_LEVELS_BY_MODULE or {}).keys())
    return {
        n: logging.getLevelName(logging.getLogger(n).getEffectiveLevel())
        for n in sorted(names)
    }
