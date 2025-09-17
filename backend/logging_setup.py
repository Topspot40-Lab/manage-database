# backend/logging_setup.py
from __future__ import annotations

import os
import sys
import logging
import logging.config
import backend.config.logging_vars as lv  # <- all vars live here

# Optional app metadata (best-effort)
try:
    from backend.config.app_cfg import APP_VERSION, LAST_UPDATED
except Exception:
    APP_VERSION, LAST_UPDATED = "dev", "n/a"


def _console_formatter():
    """
    Return a console formatter. If LOG_COLOR_ENABLED is True and colorama is
    available, it applies very light colorization (placeholders by default).
    """
    base_fmt = "%(asctime)s %(levelname)s [%(name)s] %(module)s.%(funcName)s:%(lineno)d — %(message)s"
    date_fmt = "%Y-%m-%dT%H:%M:%S"
    if lv.LOG_COLOR_ENABLED:
        try:
            from colorama import init as _cinit, Fore, Style  # type: ignore
            _cinit()

            class ColorFormatter(logging.Formatter):
                COLORS = {
                    "DEBUG": "",      # e.g., Fore.CYAN
                    "INFO": "",       # e.g., Fore.GREEN
                    "WARNING": "",    # e.g., Fore.YELLOW
                    "ERROR": "",      # e.g., Fore.RED
                    "CRITICAL": "",   # e.g., Fore.MAGENTA
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
    """
    Build and apply a dictConfig based on values in backend.config.logging_vars.
    Call this *before* importing any routers or backend modules.
    """
    # ---------------- Handlers ----------------
    handlers: dict[str, dict] = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "console",
            "level": str(lv.LOG_LEVEL).upper(),
        }
    }

    if lv.LOG_FILE_ENABLED:
        os.makedirs(os.path.dirname(lv.LOG_FILE_PATH) or ".", exist_ok=True)
        handlers["file"] = {
            "class": "logging.FileHandler",
            "filename": lv.LOG_FILE_PATH,
            "mode": "a",
            "encoding": "utf-8",
            "formatter": "standard",
            "level": str(lv.LOG_LEVEL).upper(),
        }

    if lv.ADS_LOG_FILE_ENABLED:
        os.makedirs(os.path.dirname(lv.ADS_LOG_FILE_PATH) or ".", exist_ok=True)
        handlers["ads_file"] = {
            "class": "logging.FileHandler",
            "filename": lv.ADS_LOG_FILE_PATH,
            "mode": "a",
            "encoding": "utf-8",
            "formatter": "standard",
            "level": str(lv.LOG_LEVEL_ADS).upper(),
        }

    # Which logger names count as "ads" (get extra ads_file if enabled)
    ADS_LOGGER_NAMES = {
        "backend.routers.ads_scripts",
        "backend.services.ads.script_generator",
        "backend.services.ads.ad_audio",
        "ads_scripts",  # fallback bare name
    }

    # ---------------- Loggers ----------------
    loggers: dict[str, dict] = {}

    for module_name, level_name in (lv.LOG_LEVELS_BY_MODULE or {}).items():
        level = str(level_name).upper()
        handler_list = ["console"] + (["file"] if "file" in handlers else [])
        if "ads_file" in handlers and module_name in ADS_LOGGER_NAMES:
            handler_list = ["console"] + (["ads_file"] + (["file"] if "file" in handlers else []))
        loggers[module_name] = {
            "handlers": handler_list,
            "level": level,       # dictConfig accepts string levels
            "propagate": False,   # prevent double-logging
        }

    # Force DEBUG from env list (comma-separated)
    for name in lv.DEBUG_LOGGERS:
        if not name:
            continue
        handler_list = ["console"] + (["file"] if "file" in handlers else [])
        if "ads_file" in handlers and name in ADS_LOGGER_NAMES:
            handler_list = ["console"] + (["ads_file"] + (["file"] if "file" in handlers else []))
        loggers[name] = {
            "handlers": handler_list,
            "level": "DEBUG",
            "propagate": False,
        }

    # Tidy third-party chatter (optional — only if not already overridden)
    loggers.setdefault("uvicorn.error", {"level": "INFO"})
    loggers.setdefault("uvicorn.access", {"level": "WARNING"})
    loggers.setdefault("sqlalchemy.engine", {"level": "WARNING"})
    loggers.setdefault("httpx", {"level": "WARNING"})

    # ---------------- dictConfig ----------------
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

    # Silence any lingering STEP_* loggers if they still exist anywhere
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if isinstance(name, str) and name.startswith("STEP_"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)

    logging.getLogger(__name__).info(
        "✅ Logging configured | root=%s | app=%s (updated %s)",
        logging.getLevelName(logging.getLogger().level), APP_VERSION, LAST_UPDATED
    )
