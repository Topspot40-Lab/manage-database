# backend/logging_setup.py
from __future__ import annotations

import os
import logging
import logging.config
from typing import Dict

# ── .env early so LOG_LEVEL is available ───────────────────────────────────
try:
    from dotenv import load_dotenv, find_dotenv  # pip install python-dotenv
    load_dotenv(find_dotenv(), override=False)
except Exception:
    pass

# Single source of truth for levels
import backend.config.logging_vars as lv  # your file

# Optional app metadata
try:
    from backend.config.app_cfg import APP_VERSION, LAST_UPDATED
except Exception:
    APP_VERSION, LAST_UPDATED = "dev", "n/a"

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_configured_flag = "_topsport_logging_configured"

def _normalize_level(name: str | int | None, fallback: str = "INFO") -> str:
    if isinstance(name, int):
        # accept numeric levels too
        return logging.getLevelName(name)
    if not name:
        return fallback
    up = str(name).upper()
    return up if up in _VALID_LEVELS else fallback

def _console_formatter():
    base_fmt = "%(asctime)s %(levelname)s [%(name)s] %(module)s.%(funcName)s:%(lineno)d — %(message)s"
    date_fmt = "%Y-%m-%dT%H:%M:%S"
    if getattr(lv, "LOG_COLOR_ENABLED", False):
        try:
            from colorama import init as _cinit, Fore, Style  # type: ignore
            _cinit()

            class ColorFormatter(logging.Formatter):
                COLORS = {
                    "DEBUG": Fore.BLUE,
                    "INFO": "",
                    "WARNING": Fore.YELLOW,
                    "ERROR": Fore.RED,
                    "CRITICAL": Fore.RED + Style.BRIGHT,
                }
                def format(self, record):
                    msg = super().format(record)
                    color = self.COLORS.get(record.levelname, "")
                    reset = Style.RESET_ALL if color else ""
                    return f"{color}{msg}{reset}"

            return ColorFormatter(base_fmt, datefmt=date_fmt)
        except Exception:
            pass
    return logging.Formatter(base_fmt, datefmt=date_fmt)

def _build_handlers() -> Dict[str, dict]:
    handlers: Dict[str, dict] = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "console",
            "level": "NOTSET",  # let logger/root control filtering
        }
    }

    if getattr(lv, "LOG_FILE_ENABLED", False):
        # Choose Rotating or plain FileHandler based on settings
        file_fmt = "standard"
        os.makedirs(os.path.dirname(lv.LOG_FILE_PATH) or ".", exist_ok=True)
        if getattr(lv, "LOG_FILE_ROTATE", False):
            # needs: from logging.handlers import RotatingFileHandler (via string path)
            handlers["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": lv.LOG_FILE_PATH,
                "maxBytes": getattr(lv, "LOG_FILE_MAX_BYTES", 5_000_000),
                "backupCount": getattr(lv, "LOG_FILE_BACKUP_COUNT", 3),
                "encoding": "utf-8",
                "mode": "a",
                "formatter": file_fmt,
                "level": "NOTSET",
            }
        else:
            handlers["file"] = {
                "class": "logging.FileHandler",
                "filename": lv.LOG_FILE_PATH,
                "mode": "a",
                "encoding": "utf-8",
                "formatter": file_fmt,
                "level": "NOTSET",
            }
    return handlers

def setup_logging() -> None:
    """
    Idempotent logging config. Safe to call from an app factory even under uvicorn --reload.
    Set env LOG_FORCE_RECONFIG=true to override the idempotency guard within a process.
    """
    # Idempotency guard
    if getattr(setup_logging, _configured_flag, False) and os.getenv("LOG_FORCE_RECONFIG", "").lower() not in ("1", "true", "yes", "on"):
        return

    # Normalize root level
    root_level = _normalize_level(getattr(lv, "LOG_LEVEL", None), "INFO")

    # Normalize per-module levels
    per_module = {}
    for name, lvl in (getattr(lv, "LOG_LEVELS_BY_MODULE", {}) or {}).items():
        per_module[name] = _normalize_level(lvl, root_level)

    handlers = _build_handlers()

    # Per-logger config from LOG_LEVELS_BY_MODULE
    loggers: Dict[str, dict] = {}
    for module_name, level_name in per_module.items():
        handler_list = ["console"] + (["file"] if "file" in handlers else [])
        loggers[module_name] = {
            "handlers": handler_list,
            "level": level_name,
            "propagate": False,  # prevents duplicate lines via root
        }

    # Pin common framework/library loggers
    framework_handlers = ["console"] + (["file"] if "file" in handlers else [])
    loggers.setdefault("uvicorn",         {"handlers": framework_handlers, "level": "INFO",    "propagate": False})
    loggers.setdefault("uvicorn.error",   {"handlers": framework_handlers, "level": "INFO",    "propagate": False})
    loggers.setdefault("uvicorn.access",  {"handlers": framework_handlers, "level": "WARNING", "propagate": False})
    loggers.setdefault("sqlalchemy.engine", {"handlers": framework_handlers, "level": "WARNING", "propagate": False})
    loggers.setdefault("httpx",             {"handlers": framework_handlers, "level": "WARNING", "propagate": False})

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,  # keep False to avoid silencing libs you didn't list
        "formatters": {
            "console": {"()": _console_formatter},
            "standard": {
                "format": "%(asctime)s %(levelname)s [%(name)s] %(module)s.%(funcName)s:%(lineno)d — %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": handlers,
        "loggers": loggers,
        "root": {
            "handlers": ["console"] + (["file"] if "file" in handlers else []),
            "level": root_level,
        },
    }

    # Apply configuration
    logging.config.dictConfig(LOGGING)

    # Diagnostics (only appear when effective level shows DEBUG here)
    log = logging.getLogger(__name__)
    configured_debug = sorted([n for n, lvl in per_module.items() if lvl == "DEBUG"])
    effective_debug = sorted(
        [
            name for name, lg in logging.Logger.manager.loggerDict.items()
            if isinstance(lg, logging.Logger) and lg.getEffectiveLevel() == logging.DEBUG
        ]
    )
    root_lvl_num = logging.getLogger().getEffectiveLevel()

    log.debug("🛠️ Configured DEBUG modules: %s", ", ".join(configured_debug) if configured_debug else "(none)")
    log.debug("🔎 Effective DEBUG modules (instantiated): %s", ", ".join(effective_debug) if effective_debug else "(none)")
    if root_lvl_num == logging.DEBUG:
        log.debug("🌍 Root level is DEBUG: most modules will be verbose unless pinned higher.")

    # Quiet any old STEP_* loggers if they still exist
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if isinstance(name, str) and name.startswith("STEP_"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)

    log.debug(
        "✅ Logging configured | root=%s | app=%s (updated %s) | env.LOG_LEVEL=%r",
        logging.getLevelName(root_lvl_num),
        APP_VERSION,
        LAST_UPDATED,
        os.getenv("LOG_LEVEL"),
    )

    # mark configured
    setattr(setup_logging, _configured_flag, True)
