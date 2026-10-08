"""Temp file cleanup: right after sending and periodically on a timer."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid
from pathlib import Path

from loguru import logger

from app.config import settings


def remove_path(path: Path | str | None) -> None:
    """Remove a file or directory, never raising."""
    if not path:
        return
    target = Path(path)
    try:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
    except OSError as exc:  # permissions, a race with another worker, etc.
        logger.warning("Не удалось удалить {}: {}", target, exc)


def ensure_temp_dir_writable(root: Path | None = None) -> Path:
    """Fail fast if the temp dir is not writable.

    Found the hard way: a tmpfs mount lands root-owned 0755 and shadows the
    image's chown, so a non-root process could create no job directory. Without
    this check the bot started happily and only broke on the first link, with a
    PermissionError buried in the traceback.
    """
    root = Path(root or settings.temp_dir)
    root.mkdir(parents=True, exist_ok=True)
    probe = root / f".probe-{uuid.uuid4().hex}"
    try:
        probe.mkdir()
        (probe / "probe").write_bytes(b"ok")
    except OSError as exc:
        raise RuntimeError(
            f"Temp directory {root} is not writable ({exc}). "
            f"Running as uid {os.geteuid()}; if it is a tmpfs mount, give it mode 01777."
        ) from exc
    finally:
        remove_path(probe)
    return root


def sweep_temp_dir(root: Path | None = None, max_age_sec: int | None = None) -> int:
    """Remove everything older than max_age_sec from the temp dir; returns the count."""
    root = Path(root or settings.temp_dir)
    max_age = max_age_sec if max_age_sec is not None else settings.file_max_age_sec
    if not root.exists():
        return 0

    threshold = time.time() - max_age
    removed = 0
    for entry in root.iterdir():
        try:
            if entry.stat().st_mtime >= threshold:
                continue
        except OSError:
            continue
        remove_path(entry)
        removed += 1
    if removed:
        logger.info("Очистка temp: удалено объектов — {}", removed)
    return removed


class CleanupWorker:
    """Background sweeper task - cron equivalent living inside the process."""

    def __init__(self, interval_sec: int | None = None) -> None:
        self._interval = interval_sec or settings.cleanup_interval_sec
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await asyncio.to_thread(sweep_temp_dir)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Ошибка в задаче очистки: {}", exc)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="cleanup-worker")
            logger.info("Воркер очистки запущен (интервал {} с)", self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Воркер очистки остановлен")
