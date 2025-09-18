# backend/logging_setup.py
from __future__ import annotations

import os
import logging
import logging.config

# Load .env early so LOG_LEVEL is available
try:
    from dotenv import load_dotenv, find_dotenv  # pip install python-dotenv
    load_dotenv(find_dotenv(), override=False)
except Exception:
    pass

# Single source of truth for levels
import backend.config.logging_vars as lv  # <-- your file lives here

# Optional app metadata
try:
    from backend.config.app_cfg import APP_VERSION, LAST_UPDATED
except Exception:
    APP_VERSION, LAST_UPDATED = "dev", "n/a"


def _console_formatter():
    base_fmt = "%(asctime)s %(levelname)s [%(name)s] %(module)s.%(funcName)s:%(lineno)d — %(message)s"
    date_fmt = "%Y-%m-%dT%H:%M:%S"
    if getattr(lv, "LOG_COLOR_ENABLED", False):
        try:
            from colorama import init as _cinit, Style  # type: ignore
            _cinit()

            class ColorFormatter(logging.Formatter):
                COLORS = {"DEBUG": "", "INFO": "", "WARNING": "", "ERROR": "", "CRITICAL": ""}
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
    # Handlers (leave handler level NOTSET so logger/root control filtering)
    handlers: dict[str, dict] = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "console",
            "level": "NOTSET",
        }
    }
    if getattr(lv, "LOG_FILE_ENABLED", False):
        os.makedirs(os.path.dirname(lv.LOG_FILE_PATH) or ".", exist_ok=True)
        handlers["file"] = {
            "class": "logging.FileHandler",
            "filename": lv.LOG_FILE_PATH,
            "mode": "a",
            "encoding": "utf-8",
            "formatter": "standard",
            "level": "NOTSET",
        }

    # Per-logger config — ONLY from LOG_LEVELS_BY_MODULE
    loggers: dict[str, dict] = {}
    for module_name, level_name in (lv.LOG_LEVELS_BY_MODULE or {}).items():
        handler_list = ["console"] + (["file"] if "file" in handlers else [])
        loggers[module_name] = {
            "handlers": handler_list,
            "level": str(level_name).upper(),
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
            "handlers": ["console"] + (["file"] if "file" in handlers else []),
            "level": str(lv.LOG_LEVEL).upper(),
        },
    }

    logging.config.dictConfig(LOGGING)

    # After logging is configured — show configured vs effective DEBUG modules
    configured_debug = sorted(
        [name for name, lvl in (lv.LOG_LEVELS_BY_MODULE or {}).items()
         if str(lvl).upper() == "DEBUG"]
    )

    effective_debug = sorted(
        [
            name for name, lg in logging.Logger.manager.loggerDict.items()
            if isinstance(lg, logging.Logger) and lg.getEffectiveLevel() == logging.DEBUG
        ]
    )

    log = logging.getLogger(__name__)
    root_lvl = logging.getLogger().getEffectiveLevel()

    log.info("🛠️ Configured DEBUG modules: %s",
             ", ".join(configured_debug) if configured_debug else "(none)")
    log.info("🔎 Effective DEBUG modules (instantiated): %s",
             ", ".join(effective_debug) if effective_debug else "(none)")
    if root_lvl == logging.DEBUG:
        log.info("🌍 Root level is DEBUG: most modules will be verbose unless pinned higher.")

    # If STEP_* loggers no longer exist, you can remove this; harmless if left.
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if isinstance(name, str) and name.startswith("STEP_"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)

    logging.getLogger(__name__).info(
        "✅ Logging configured | root=%s | app=%s (updated %s) | env.LOG_LEVEL=%r",
        logging.getLevelName(logging.getLogger().level),
        APP_VERSION,
        LAST_UPDATED,
        os.getenv("LOG_LEVEL"),
    )
