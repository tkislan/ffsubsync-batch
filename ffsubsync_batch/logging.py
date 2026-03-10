from __future__ import annotations

import logging
import sys

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("sync_subtitles")
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    logger.addHandler(console)

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    logger.addHandler(fh)

    return logger
