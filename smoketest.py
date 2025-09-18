import logging, os
level = os.getenv("LOG_LEVEL","INFO").upper()
logging.basicConfig(level=getattr(logging, level), format="%(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("smoketest")
log.debug("debug visible?")
log.info("info visible!")
