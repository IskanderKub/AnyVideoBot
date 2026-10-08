"""Database operations. A database error must not break the main bot flow, so
callers go through the safe helpers below (see `log_*`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select

from app.db.models import Download, DownloadStatus, User, utcnow
from app.db.session import session_scope


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
) -> int | None:
    """Return the internal user id, creating the row on first contact."""
    try:
        async with session_scope() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user is None:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    language_code=language_code,
                )
                session.add(user)
                await session.flush()
            else:
                user.username = username
                user.first_name = first_name
                user.last_seen_at = utcnow()
            return user.id
    except Exception as exc:
        logger.error("БД: не удалось получить/создать пользователя {}: {}", telegram_id, exc)
        return None


async def log_download_start(user_id: int | None, url: str, platform: str) -> int | None:
    if user_id is None:
        return None
    try:
        async with session_scope() as session:
            record = Download(
                user_id=user_id, url=url, platform=platform, status=DownloadStatus.PENDING
            )
            session.add(record)
            await session.flush()
            return record.id
    except Exception as exc:
        logger.error("БД: не удалось записать начало скачивания: {}", exc)
        return None


async def log_download_finish(
    download_id: int | None,
    status: DownloadStatus,
    *,
    title: str | None = None,
    duration_sec: int | None = None,
    file_size_bytes: int | None = None,
    elapsed_ms: int | None = None,
    error: str | None = None,
) -> None:
    if download_id is None:
        return
    try:
        async with session_scope() as session:
            record = await session.get(Download, download_id)
            if record is None:
                return
            record.status = status
            record.title = title
            record.duration_sec = duration_sec
            record.file_size_bytes = file_size_bytes
            record.elapsed_ms = elapsed_ms
            record.error = (error or None) and error[:1000]
    except Exception as exc:
        logger.error("БД: не удалось записать результат скачивания: {}", exc)


async def collect_stats() -> dict[str, Any]:
    """Summary for GET /stats."""
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    async with session_scope() as session:
        total_users = await session.scalar(select(func.count(User.id))) or 0
        total_downloads = await session.scalar(select(func.count(Download.id))) or 0
        successful = (
            await session.scalar(
                select(func.count(Download.id)).where(Download.status == DownloadStatus.SUCCESS)
            )
            or 0
        )
        failed = (
            await session.scalar(
                select(func.count(Download.id)).where(Download.status == DownloadStatus.FAILED)
            )
            or 0
        )
        last_24h = (
            await session.scalar(
                select(func.count(Download.id)).where(Download.created_at >= day_ago)
            )
            or 0
        )
        avg_ms = await session.scalar(
            select(func.avg(Download.elapsed_ms)).where(
                Download.status == DownloadStatus.SUCCESS
            )
        )
        by_platform = dict(
            (
                await session.execute(
                    select(Download.platform, func.count(Download.id)).group_by(Download.platform)
                )
            ).all()
        )

    return {
        "users_total": total_users,
        "downloads_total": total_downloads,
        "downloads_success": successful,
        "downloads_failed": failed,
        "downloads_last_24h": last_24h,
        "success_rate": round(successful / total_downloads, 3) if total_downloads else None,
        "avg_elapsed_ms": int(avg_ms) if avg_ms else None,
        "by_platform": by_platform,
    }
