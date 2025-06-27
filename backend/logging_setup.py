import logging
import sys
import os
from datetime import datetime

from backend.config import (
    LOG_LEVEL,
    LOG_LEVELS_BY_MODULE,
    LOG_FILE_ENABLED,
    LOG_COLOR_ENABLED,
    LOG_FILE_PATH,
    LOG_SUMMARY_ENABLED,
    APP_VERSION,
    LAST_UPDATED
)

# 🎨 Module-specific colors and emojis
MODULE_STYLES = {
    "xai_service":     {"color": "bold_green",   "emoji": "🧠"},
    "spotify_service": {"color": "bold_blue",    "emoji": "🎵"},
    "track_builder":   {"color": "bold_yellow",  "emoji": "🛠️"},
    "track_logging":   {"color": "bold_cyan",    "emoji": "📝"},
    "generate_json":   {"color": "bold_magenta", "emoji": "📦"},
    "__main__":        {"color": "white",        "emoji": "🚀"},
}

# 🐞 Level-based fallback emojis (used in file logs)
LEVEL_TAGS = {
    "DEBUG": "🐞",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🔥"
}

def _get_color_code(color_name):
    color_map = {
        "black": "30", "red": "31", "green": "32", "yellow": "33", "blue": "34",
        "magenta": "35", "cyan": "36", "white": "37",
        "bold_red": "1;31", "bold_green": "1;32", "bold_yellow": "1;33",
        "bold_blue": "1;34", "bold_magenta": "1;35", "bold_cyan": "1;36",
    }
    return color_map.get(color_name, "37")

def inject_module_style(record):
    style = MODULE_STYLES.get(record.module, {"color": "white", "emoji": "🔍"})
    module_color_code = _get_color_code(style["color"])
    setattr(record, "module_color", f"\033[{module_color_code}m")
    setattr(record, "emoji", style["emoji"])
    setattr(record, "reset", "\033[0m")

def setup_logging():
    handlers = []

    # Try importing colorlog
    try:
        from colorlog import ColoredFormatter
    except ImportError:
        class ColoredFormatter(logging.Formatter): pass
        print("⚠️  colorlog not installed. Run `pip install colorlog` for color support.")

    class ModuleAwareColoredFormatter(ColoredFormatter):
        def format(self, record):
            inject_module_style(record)
            return super().format(record)

    # Format string for console
    formatter_string = "%(asctime)s [%(levelname)s] %(emoji)s [%(module_color)s%(module)s.%(funcName)s:%(lineno)d%(reset)s]\n   %(message)s\n"

    if LOG_COLOR_ENABLED:
        formatter = ModuleAwareColoredFormatter(
            "%(log_color)s" + formatter_string,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            }
        )
    else:
        formatter = logging.Formatter(formatter_string)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # Optional: File handler (emoji + plain format)
    if LOG_FILE_ENABLED:
        log_dir = os.path.dirname(LOG_FILE_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        class EmojiFileFormatter(logging.Formatter):
            def format(self, record):
                # Use fallback emoji if not in module style
                style = MODULE_STYLES.get(record.module, {"emoji": LEVEL_TAGS.get(record.levelname, "❔")})
                record.emoji = style["emoji"]
                return super().format(record)

        file_formatter_string = "%(asctime)s [%(levelname)s] %(emoji)s [%(module)s.%(funcName)s:%(lineno)d]\n   %(message)s\n"
        file_formatter = EmojiFileFormatter(file_formatter_string)

        file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # Set up logging globally
    logging.basicConfig(
        level=LOG_LEVEL,
        handlers=handlers,
        force=True
    )

    # Set per-module levels
    for module_name, level_name in LOG_LEVELS_BY_MODULE.items():
        logger = logging.getLogger(module_name)
        try:
            logger.setLevel(getattr(logging, level_name.upper()))
        except AttributeError:
            logger.setLevel(logging.INFO)
            logging.getLogger(__name__).warning(
                f"⚠️ Invalid log level '{level_name}' for module '{module_name}', defaulting to INFO."
            )

    logging.getLogger(__name__).info("✅ Logging setup complete.")

    # Optional summary log
    if LOG_SUMMARY_ENABLED:
        summary_lines = [
            "🛠️  Logging Setup Summary",
            f"├─ App Version: {APP_VERSION} (Last updated: {LAST_UPDATED})",
            f"├─ Startup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"├─ Global Log Level: {LOG_LEVEL}"
        ]

        if LOG_LEVELS_BY_MODULE:
            summary_lines.append("├─ Module Overrides:")

            for module_name, configured_level_str in LOG_LEVELS_BY_MODULE.items():
                logger_obj = logging.getLogger(module_name)
                effective_level = logging.getLevelName(logger_obj.getEffectiveLevel())
                configured_level = logging.getLevelName(logger_obj.level) if logger_obj.level else "NOT SET"

                # Add test debug line to confirm it works
                logger_obj.debug(f"✅ DEBUG ACTIVE for {module_name} — logger.name = {logger_obj.name}")

                summary_lines.append(
                    f"│   ├─ {module_name}: Configured={configured_level_str.upper()}, "
                    f"Set={configured_level}, Effective={effective_level}"
                )
        else:
            summary_lines.append("├─ No module-level overrides defined.")

        summary_logger = logging.getLogger(__name__)
        for line in summary_lines:
            summary_logger.info(line)

        try:
            report_path = "logs/logging_report.txt"
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                for line in summary_lines:
                    f.write(line + "\n")
        except Exception as e:
            summary_logger.warning(f"⚠️ Could not write logging summary to file: {e}")
