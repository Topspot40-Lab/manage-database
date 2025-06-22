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


def setup_logging():
    handlers = []

    # ✅ Try importing colorlog
    try:
        from colorlog import ColoredFormatter
    except ImportError:
        class ColoredFormatter(logging.Formatter):  # fallback
            pass
        print("⚠️  colorlog not installed. Run `pip install colorlog` for color support.")

    # 🎨 Select formatter with function, module, line info
    formatter_string = "%(asctime)s [%(levelname)s] [%(module)s.%(funcName)s:%(lineno)d] %(message)s\n"

    colored_formatter_class = ColoredFormatter if LOG_COLOR_ENABLED else None

    if LOG_COLOR_ENABLED and colored_formatter_class and colored_formatter_class != logging.Formatter:
        formatter = colored_formatter_class(
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

    # 🖥️ Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # 🗂️ Optional file handler
    if LOG_FILE_ENABLED:
        log_dir = os.path.dirname(LOG_FILE_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
        file_formatter = logging.Formatter(formatter_string)
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # 🔧 Set global log level
    logging.basicConfig(
        level=LOG_LEVEL,
        handlers=handlers,
        force=True
    )

    # 🎯 Apply per-module overrides
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

    # 📋 Optional: Logging summary
    if LOG_SUMMARY_ENABLED:
        summary_lines = [
            "🛠️  Logging Setup Summary",
            f"├─ App Version: {APP_VERSION} (Last updated: {LAST_UPDATED})",
            f"├─ Startup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"├─ Global Log Level: {LOG_LEVEL}"
        ]

        if LOG_LEVELS_BY_MODULE:
            summary_lines.append("├─ Module Overrides:")
            for module_name in LOG_LEVELS_BY_MODULE:
                logger_obj = logging.getLogger(module_name)
                configured_level = logger_obj.level
                effective_level = logging.getLevelName(logger_obj.getEffectiveLevel())

                if configured_level == 0:
                    summary_lines.append(
                        f"│   ├─ {module_name}: not set (effective: {effective_level})"
                    )
                else:
                    configured_level_name = logging.getLevelName(configured_level)
                    summary_lines.append(
                        f"│   ├─ {module_name}: {configured_level_name} (effective: {effective_level})"
                    )
        else:
            summary_lines.append("├─ No module-level overrides defined.")

        summary_logger = logging.getLogger(__name__)
        for line in summary_lines:
            summary_logger.info(line)

        # 📝 Save summary to logs/logging_report.txt
        try:
            report_path = "logs/logging_report.txt"
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                for line in summary_lines:
                    f.write(line + "\n")
        except Exception as e:
            summary_logger.warning(f"⚠️ Could not write logging summary to file: {e}")
