"""Logging setup on loguru, intercepting the standard logging module."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    """Redirects standard logging records (uvicorn, aiogram) into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=level.upper(),
        backtrace=False,
        diagnose=False,
        enqueue=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            path,
            level=level.upper(),
            rotation="10 MB",
            retention=5,
            encoding="utf-8",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "aiogram", "sqlalchemy.engine"):
        std_logger = logging.getLogger(name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False
