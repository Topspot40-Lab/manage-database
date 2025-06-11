# backend/logging_setup.py

import logging
import sys
from backend.config import (
    LOG_LEVEL,
    LOG_LEVELS_BY_MODULE,
    LOG_FILE_ENABLED,
    LOG_COLOR_ENABLED,
    LOG_FILE_PATH
)

def setup_logging():
    handlers = []

    # ✅ Import or define fallback
    try:
        from colorlog import ColoredFormatter
    except ImportError:
        class ColoredFormatter(logging.Formatter):  # Fallback dummy class
            pass
        print("⚠️  colorlog not installed. Run `pip install colorlog` for color support.")

    # Assign lowercase variable either way
    colored_formatter_class = ColoredFormatter if LOG_COLOR_ENABLED else None

    # 🎨 Console formatter
    if LOG_COLOR_ENABLED and colored_formatter_class and colored_formatter_class != logging.Formatter:
        formatter = colored_formatter_class(
            "%(log_color)s%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            }
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # File handler
    if LOG_FILE_ENABLED:
        file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")  # ✅ FIXED HERE
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # Apply config
    logging.basicConfig(
        level=LOG_LEVEL,
        handlers=handlers,
        force=True
    )

    # Per-module overrides
    for module_name, level_name in LOG_LEVELS_BY_MODULE.items():
        logger = logging.getLogger(module_name)
        try:
            logger.setLevel(getattr(logging, level_name.upper()))
        except AttributeError:
            logger.setLevel(logging.INFO)
            logging.getLogger(__name__).warning(
                f"⚠️ Invalid log level '{level_name}' for module '{module_name}', defaulting to INFO."
            )

    logging.getLogger(__name__).info("Logging setup complete.")

