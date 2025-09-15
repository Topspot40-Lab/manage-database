# backend/logging_setup.py
"""
Central logging configuration (module-only).
- Console (optional color) + optional file logging.
- Root level from env (LOG_LEVEL).
- Per-module levels from config.LOG_LEVELS_BY_MODULE.
- Extra DEBUG knobs via config.DEBUG_LOGGERS (comma-separated env).
- STEP_* loggers are explicitly silenced if any remain in code.
"""

import os
import sys
import logging
import logging.config

from backend.config import (
    APP_VERSION, LAST_UPDATED,
    LOG_LEVEL, LOG_LEVELS_BY_MODULE,
    LOG_FILE_ENABLED, LOG_COLOR_ENABLED, LOG_FILE_PATH,
    DEBUG_LOGGERS,
)

# Lightweight ANSI color support (no hard dependency)
def _console_formatter():
    base_fmt = "%(asctime)s %(levelname)s [%(name)s] %(module)s.%(funcName)s:%(lineno)d — %(message)s"
    date_fmt = "%Y-%m-%dT%H:%M:%S"
    if LOG_COLOR_ENABLED:
        try:
            from colorama import init as _cinit, Fore, Style
            _cinit()

            class ColorFormatter(logging.Formatter):
                COLORS = {
                    "DEBUG": "",            # Fore.CYAN
                    "INFO": "",             # Fore.GREEN
                    "WARNING": "",          # Fore.YELLOW
                    "ERROR": "",            # Fore.RED
                    "CRITICAL": "",         # Fore.MAGENTA
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

def setup_logging() -> None:
    handlers = {}

    # Console handler
    handlers["console"] = {
        "class": "logging.StreamHandler",
        "stream": sys.stdout,
        "formatter": "console",
    }

    # Optional file handler
    if LOG_FILE_ENABLED:
        os.makedirs(os.path.dirname(LOG_FILE_PATH) or ".", exist_ok=True)
        handlers["file"] = {
            "class": "logging.FileHandler",
            "filename": LOG_FILE_PATH,
            "mode": "a",
            "encoding": "utf-8",
            "formatter": "standard",
        }

    # Build logger map from per-module overrides
    loggers = {}
    for module_name, level_name in (LOG_LEVELS_BY_MODULE or {}).items():
        lvl = getattr(logging, str(level_name).upper(), logging.INFO)
        loggers[module_name] = {
            "handlers": ["console"] + (["file"] if LOG_FILE_ENABLED else []),
            "level": lvl,
            "propagate": False,
        }

    # Force DEBUG via env list (comma-separated names)
    for name in DEBUG_LOGGERS:
        if name:
            loggers[name] = {
                "handlers": ["console"] + (["file"] if LOG_FILE_ENABLED else []),
                "level": "DEBUG",
                "propagate": False,
            }

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
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
            "handlers": ["console"] + (["file"] if LOG_FILE_ENABLED else []),
            "level": getattr(logging, str(LOG_LEVEL).upper(), logging.INFO),
        },
    }

    logging.config.dictConfig(LOGGING)

    # Silence any lingering STEP_* loggers if they still exist anywhere
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if isinstance(name, str) and name.startswith("STEP_"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)

    logging.getLogger(__name__).info(
        "✅ Logging configured | root=%s | app=%s (updated %s)",
        logging.getLevelName(logging.getLogger().level), APP_VERSION, LAST_UPDATED
    )
