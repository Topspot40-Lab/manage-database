from __future__ import annotations

import os
import logging
import logging.config
from typing import Dict

# -------------------------------------------------------------------
# GLOBAL IDENTITY GUARD – works even with uvicorn reload
# -------------------------------------------------------------------
# We store a marker in the *actual logging module*, not in globals().
# This survives module reloads, preventing duplicate handler creation.
if not hasattr(logging, "_topspot_logging_initialized"):
    logging._topspot_logging_initialized = False

# -------------------------------------------------------------------
# Load .env early
# -------------------------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except Exception:
    pass

# Config vars
import backend.config.logging_vars as lv

try:
    from backend.config.app_cfg import APP_VERSION, LAST_UPDATED
except Exception:
    APP_VERSION, LAST_UPDATED = "dev", "n/a"


_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _normalize_level(name, fallback="INFO"):
    if isinstance(name, int):
        return logging.getLevelName(name)
    if not name:
        return fallback
    up = str(name).upper()
    return up if up in _VALID_LEVELS else fallback


def _console_formatter():
    base_fmt = (
        "%(asctime)s %(levelname)s [%(name)s] "
        "%(module)s.%(funcName)s:%(lineno)d — %(message)s"
    )
    date_fmt = "%Y-%m-%dT%H:%M:%S"

    if getattr(lv, "LOG_COLOR_ENABLED", False):
        try:
            from colorama import init as _cinit, Fore, Style
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


def _build_handlers():
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "console",
            "level": "NOTSET",
        }
    }

    if getattr(lv, "LOG_FILE_ENABLED", False):
        file_fmt = "standard"
        os.makedirs(os.path.dirname(lv.LOG_FILE_PATH) or ".", exist_ok=True)

        if getattr(lv, "LOG_FILE_ROTATE", False):
            handlers["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": lv.LOG_FILE_PATH,
                "maxBytes": getattr(lv, "LOG_FILE_MAX_BYTES", 5_000_000),
                "backupCount": getattr(lv, "LOG_FILE_BACKUP_COUNT", 3),
                "encoding": "utf-8",
                "formatter": file_fmt,
            }
        else:
            handlers["file"] = {
                "class": "logging.FileHandler",
                "filename": lv.LOG_FILE_PATH,
                "encoding": "utf-8",
                "formatter": file_fmt,
            }

    return handlers


def setup_logging() -> None:
    """
    Fully idempotent logging config.
    Prevents handler duplication even with uvicorn reload.
    """
    # If already initialized and not forced, stop here.
    if logging._topspot_logging_initialized and os.getenv(
        "LOG_FORCE_RECONFIG", ""
    ).lower() not in ("1", "true", "yes", "on"):
        return

    logging._topspot_logging_initialized = True

    root_level = _normalize_level(getattr(lv, "LOG_LEVEL", None), "INFO")

    # Per-module overrides
    per_module = {
        name: _normalize_level(level, root_level)
        for name, level in (getattr(lv, "LOG_LEVELS_BY_MODULE", {}) or {}).items()
    }

    handlers = _build_handlers()

    # Build logger list
    loggers = {
        # Prevent Uvicorn from double-printing
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "WARNING", "propagate": False},

        # HTTPX and SQLAlchemy chatter
        "sqlalchemy.engine": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "httpx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    }

    # Add your per-module settings
    for module, level in per_module.items():
        loggers[module] = {
            "handlers": ["console"] + (["file"] if "file" in handlers else []),
            "level": level,
            "propagate": False,  # CRUCIAL FIX
        }

    LOGGING = {
        "version": 1,
        # Prevent the default handlers from being wiped, but stop duplication
        "disable_existing_loggers": False,
        "formatters": {
            "console": {"()": _console_formatter},
            "standard": {
                "format": "%(asctime)s %(levelname)s [%(name)s] "
                          "%(module)s.%(funcName)s:%(lineno)d — %(message)s",
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

    logging.config.dictConfig(LOGGING)

    # One-time boot message
    log = logging.getLogger(__name__)
    log.info("🟢 Logging initialized — TopSpot %s (updated %s)", APP_VERSION, LAST_UPDATED)
