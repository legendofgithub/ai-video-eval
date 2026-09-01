# -*- coding: utf-8 -*-
"""Application logger: console + rotating file under data/app.log."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def _app_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_BASE = _app_base()
_LOG_PATH = os.path.join(_BASE, "data", "app.log")


def get_logger(name="videoeval"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # PyInstaller --windowed exes have no stderr; skip the console handler.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)

    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        fileh = RotatingFileHandler(_LOG_PATH, maxBytes=2_000_000,
                                    backupCount=2, encoding="utf-8")
        fileh.setFormatter(fmt)
        logger.addHandler(fileh)
    except OSError:
        pass  # read-only install: console-only logging
    return logger
