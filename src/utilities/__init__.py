import logging
import sys
from datetime import datetime, timezone

from env_vars import DEBUG_LOG_TO_CONSOLE, DEBUG_LOG_TO_DB, DEBUG_LOG_TO_FILE

logger = logging.getLogger("agent")


# Console logging setup
if DEBUG_LOG_TO_CONSOLE:
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.setLevel(logging.DEBUG)  # Set the minimum level globally
        logger.addHandler(handler)
        logger.propagate = True

# File logging setup
if DEBUG_LOG_TO_FILE:
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        file_handler = logging.FileHandler(DEBUG_LOG_TO_FILE.strip(), mode="a")
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.setLevel(logging.DEBUG)  # Set the minimum level globally
        logger.addHandler(file_handler)
