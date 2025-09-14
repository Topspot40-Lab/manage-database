# backend/logging_setup.py
"""
Central logging configuration.
- Colorful console (optional) + emoji file logs (optional).
- Root level from env (LOG_LEVEL).
- Per-module levels from config.LOG_LEVELS_BY_MODULE.
- Extra DEBUG knobs via config.DEBUG_LOGGERS (comma-separated env).
- Step-wise loggers (STEP_1, STEP_1.A, ...) from config.STEP_LOG_LEVELS.
"""

import logging
import sys
import os
from datetime import datetime

from backend.config import (
    # App/meta
    APP_VERSION, LAST_UPDATED,
    # Levels & routing
    LOG_LEVEL, LOG_LEVELS_BY_MODULE, STEP_LOG_LEVELS,
    # Extras
    LOG_FILE_ENABLED, LOG_COLOR_ENABLED, LOG_FILE_PATH, LOG_SUMMARY_ENABLED,
    # NEW: arbitrary DEBUG list from env
    DEBUG_LOGGERS,
)

# 🎨 Module-specific colors and emojis (keyed by "record.module", i.e., filename w/o package)
MODULE_STYLES = {
    "xai_service":     {"color": "bold_green",   "emoji": "🧠"},
    "spotify_service": {"color": "bold_blue",    "emoji": "🎵"},
    "track_builder":   {"color": "bold_yellow",  "emoji": "🛠️"},
    "track_logging":   {"color": "bold_cyan",    "emoji": "📝"},
    "generate_json":   {"color": "bold_magenta", "emoji": "📦"},
    "__main__":        {"color": "white",        "emoji": "🚀"},
}
# 🐞 Level-based fallback emojis (used by file handler)
LEVEL_TAGS = {"DEBUG":"🐞","INFO":"ℹ️","WARNING":"⚠️","ERROR":"❌","CRITICAL":"🔥"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get_color_code(color_name: str) -> str:
    color_map = {
        "black":"30","red":"31","green":"32","yellow":"33","blue":"34","magenta":"35","cyan":"36","white":"37",
        "bold_red":"1;31","bold_green":"1;32","bold_yellow":"1;33","bold_blue":"1;34","bold_magenta":"1;35","bold_cyan":"1;36",
    }
    return color_map.get(color_name, "37")

def _inject_module_style(record: logging.LogRecord) -> None:
    style = MODULE_STYLES.get(record.module, {"color": "white", "emoji": "🔍"})
    setattr(record, "module_color", f"\033[{_get_color_code(style['color'])}m")
    setattr(record, "emoji", style["emoji"])
    setattr(record, "reset", "\033[0m")

def _configure_step_loggers() -> None:
    # Ensure parent steps (e.g., STEP_1) get set before children (e.g., STEP_1.A)
    for step_id in sorted((k for k in STEP_LOG_LEVELS.keys() if isinstance(k, str)), key=lambda k: (k.count("."), k)):
        level_name = str(STEP_LOG_LEVELS[step_id]).upper()
        logging.getLogger(step_id).setLevel(getattr(logging, level_name, logging.INFO))

def _apply_per_module_levels() -> None:
    for module_name, level_name in LOG_LEVELS_BY_MODULE.items():
        logger = logging.getLogger(module_name)
        try:
            logger.setLevel(getattr(logging, level_name.upper()))
        except AttributeError:
            logger.setLevel(logging.INFO)
            logging.getLogger(__name__).warning(
                "⚠️ Invalid log level '%s' for module '%s'; defaulting to INFO.",
                level_name, module_name
            )

def _apply_debug_loggers() -> None:
    # Force DEBUG on any logger names provided via env (DEBUG_LOGGERS)
    for name in DEBUG_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)


# ─────────────────────────────────────────────────────────────────────────────
# Main setup
# ─────────────────────────────────────────────────────────────────────────────
def setup_logging() -> None:
    handlers: list[logging.Handler] = []

    # Try importing colorlog; fall back gracefully
    try:
        from colorlog import ColoredFormatter
    except ImportError:
        class ColoredFormatter(logging.Formatter):  # type: ignore
            pass
        print("⚠️  colorlog not installed. Run `pip install colorlog` for console colors.")

    class ModuleAwareColoredFormatter(ColoredFormatter):  # type: ignore
        def format(self, record: logging.LogRecord) -> str:
            _inject_module_style(record)
            return super().format(record)

    # Console formatter
    base_fmt = "%(asctime)s [%(levelname)s] %(emoji)s [%(module_color)s%(module)s.%(funcName)s:%(lineno)d%(reset)s]\n   %(message)s\n"
    if LOG_COLOR_ENABLED:
        console_formatter = ModuleAwareColoredFormatter(
            "%(log_color)s" + base_fmt,
            log_colors={"DEBUG":"cyan","INFO":"green","WARNING":"yellow","ERROR":"red","CRITICAL":"bold_red"}
        )
    else:
        console_formatter = logging.Formatter(base_fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)

    # Optional file handler (UTF-8 + emoji)
    if LOG_FILE_ENABLED:
        log_dir = os.path.dirname(LOG_FILE_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        class EmojiFileFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                style = MODULE_STYLES.get(record.module, {"emoji": LEVEL_TAGS.get(record.levelname, "❔")})
                record.emoji = style["emoji"]
                return super().format(record)

        file_fmt = "%(asctime)s [%(levelname)s] %(emoji)s [%(name)s -> %(module)s.%(funcName)s:%(lineno)d]\n   %(message)s\n"
        file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
        file_handler.setFormatter(EmojiFileFormatter(file_fmt))
        handlers.append(file_handler)

    # Convert root level string → numeric
    root_level = getattr(logging, str(LOG_LEVEL).upper(), logging.INFO)

    # Install handlers + root level
    logging.basicConfig(level=root_level, handlers=handlers, force=True)

    # Apply overrides
    _apply_per_module_levels()
    _apply_debug_loggers()
    _configure_step_loggers()

    logging.getLogger(__name__).info("✅ Logging setup complete (root=%s).", logging.getLevelName(root_level))

    # Optional startup summary
    if LOG_SUMMARY_ENABLED:
        _emit_logging_summary()


# ─────────────────────────────────────────────────────────────────────────────
# Summary (optional)
# ─────────────────────────────────────────────────────────────────────────────
def _emit_logging_summary() -> None:
    summary_logger = logging.getLogger(__name__)

    lines = [
        "🛠️  Logging Setup Summary",
        f"├─ App Version: {APP_VERSION} (Last updated: {LAST_UPDATED})",
        f"├─ Startup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"├─ Global Log Level: {LOG_LEVEL}",
        "├─ Module Overrides:",
    ]
    if LOG_LEVELS_BY_MODULE:
        for module_name, configured in LOG_LEVELS_BY_MODULE.items():
            lg = logging.getLogger(module_name)
            effective = logging.getLevelName(lg.getEffectiveLevel())
            configured_name = logging.getLevelName(lg.level) if lg.level else "NOT SET"
            # Emit one DEBUG line per logger so you can see it tick in the file when DEBUG is active
            lg.debug("✅ DEBUG ACTIVE for %s — logger.name=%s", module_name, lg.name)
            lines.append(f"│   ├─ {module_name}: Configured={configured.upper()}, Set={configured_name}, Effective={effective}")
    else:
        lines.append("│   └─ (none)")

    if DEBUG_LOGGERS:
        lines.append(f"├─ Forced DEBUG via env: {', '.join(DEBUG_LOGGERS)}")
    else:
        lines.append("├─ Forced DEBUG via env: (none)")

    for line in lines:
        summary_logger.info(line)

    # Write a quick report (non-fatal if it fails)
    try:
        report_path = "logs/logging_report.txt"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
    except Exception as e:
        summary_logger.warning("⚠️ Could not write logging summary to file: %s", e)
