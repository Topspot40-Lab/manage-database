# log_test.py

from backend.logging_setup import setup_logging
import logging

# Simulate different modules
xai_logger = logging.getLogger("backend.services.xai_service")
spotify_logger = logging.getLogger("backend.services.spotify_service")
utils_logger = logging.getLogger("backend.services.utils")
root_logger = logging.getLogger()

def main():
    setup_logging()

    print("🧪 Testing logging output...\n")

    root_logger.debug("ROOT: Debug message (should show if LOG_LEVEL=DEBUG)")
    root_logger.info("ROOT: Info message")
    root_logger.warning("ROOT: Warning message")
    root_logger.error("ROOT: Error message")

    xai_logger.debug("XAI: Debug log from xai_service")
    xai_logger.info("XAI: Info log from xai_service")
    xai_logger.warning("XAI: Warning log from xai_service")

    spotify_logger.debug("SPOTIFY: Debug log from spotify_service (should NOT show if level=WARNING)")
    spotify_logger.info("SPOTIFY: Info log from spotify_service")
    spotify_logger.warning("SPOTIFY: Warning log from spotify_service")

    utils_logger.debug("UTILS: Debug log from utils (should show if level=INFO or lower)")
    utils_logger.info("UTILS: Info log from utils")
    utils_logger.warning("UTILS: Warning log from utils")

    print("\n🧾 Check the console and `topspot.log` for output.")

if __name__ == "__main__":
    main()
