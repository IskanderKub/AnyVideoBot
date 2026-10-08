"""Entry point: FastAPI + aiogram webhook (or polling for local development)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from aiogram.exceptions import TelegramConflictError
from aiogram.types import Update
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.bot.dispatcher import create_bot, create_dispatcher, setup_bot_commands
from app.config import settings
from app.db.repository import collect_stats
from app.db.session import close_db, init_db
from app.services.cleanup import CleanupWorker, ensure_temp_dir_writable, sweep_temp_dir
from app.services.rate_limiter import close_rate_limiter

# Background update-handling tasks: keep references, or the GC may kill a task.
_background_tasks: set[asyncio.Task[Any]] = set()

# Delay before restarting polling after a failure: grows up to POLLING_RETRY_MAX_SEC.
POLLING_RETRY_START_SEC = 1
POLLING_RETRY_MAX_SEC = 30


async def _polling_supervisor(dp: Any, bot: Any) -> None:
    """Keeps long polling alive.

    The task used to be fire-and-forget: any exception - say a 409 Conflict when
    another process already listens on getUpdates, routine under uvicorn --reload -
    killed polling silently, and the bot stopped answering for good while the HTTP
    server stayed up.
    """
    delay = POLLING_RETRY_START_SEC
    while True:
        try:
            # handle_signals=False: uvicorn owns the signals, not aiogram.
            await dp.start_polling(bot, handle_signals=False)
            logger.info("Polling штатно остановлен")
            return
        except asyncio.CancelledError:
            raise
        except TelegramConflictError:
            logger.warning(
                "getUpdates занят другой копией бота (перезапуск или второй процесс). "
                "Повтор через {} с",
                delay,
            )
        except Exception:
            logger.exception("Polling упал, перезапуск через {} с", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, POLLING_RETRY_MAX_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.utils.logging import setup_logging

    setup_logging(settings.log_level, settings.log_file)
    logger.info("Запуск сервиса, режим: {}", settings.run_mode)

    ensure_temp_dir_writable()
    sweep_temp_dir()  # clear leftovers from the previous run
    await init_db()

    bot = create_bot()
    dp = create_dispatcher()
    app.state.bot = bot
    app.state.dp = dp

    me = await bot.get_me()
    logger.info("Бот авторизован: @{} (id={})", me.username, me.id)
    if not me.can_read_all_group_messages:
        # With privacy mode on, Telegram only delivers commands, replies to the bot
        # and mentions - a plain "@link <url>" message never reaches it.
        logger.warning(
            "Privacy mode включён: в группах сработает только упоминание @{}. "
            "Чтобы работал триггер {}, выключите его у @BotFather "
            "(/mybots -> Bot Settings -> Group Privacy -> Turn off) и заново добавьте бота в чат.",
            me.username,
            settings.group_trigger_list[0],
        )
    await setup_bot_commands(bot)

    cleanup_worker = CleanupWorker()
    cleanup_worker.start()
    app.state.cleanup_worker = cleanup_worker

    polling_task: asyncio.Task[None] | None = None
    if settings.use_webhook:
        await bot.set_webhook(
            url=settings.full_webhook_url,
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=settings.should_drop_pending_updates,
            allowed_updates=dp.resolve_used_update_types(),
        )
        logger.info("Вебхук установлен: {}", settings.full_webhook_url)
    else:
        await bot.delete_webhook(drop_pending_updates=settings.should_drop_pending_updates)
        polling_task = asyncio.create_task(_polling_supervisor(dp, bot), name="polling")
        app.state.polling_task = polling_task
        logger.info("Запущен long polling (режим разработки)")

    try:
        yield
    finally:
        logger.info("Остановка сервиса…")
        if polling_task is not None:
            try:
                await dp.stop_polling()
            except RuntimeError:
                # The poller is already stopped (it may have died) - no reason to
                # fail the shutdown over it.
                logger.debug("stop_polling: polling уже не запущен")
            polling_task.cancel()
            await asyncio.gather(polling_task, return_exceptions=True)

        for task in list(_background_tasks):
            task.cancel()
        await asyncio.gather(*_background_tasks, return_exceptions=True)

        await cleanup_worker.stop()
        sweep_temp_dir(max_age_sec=0)
        await bot.session.close()
        await close_rate_limiter()
        await close_db()
        logger.info("Сервис остановлен")


app = FastAPI(
    title="Video Download Bot",
    description="Telegram bot that downloads videos from YouTube, Instagram, TikTok and Pinterest",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/webhook/{secret_token}", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    secret_token: str,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    """Receives updates from Telegram.

    Answers 200 immediately and moves handling into a background task: a download
    outlives the Telegram timeout, and the update would otherwise be retried.
    """
    if settings.webhook_secret:
        if secret_token != settings.webhook_secret or (
            x_telegram_bot_api_secret_token
            and x_telegram_bot_api_secret_token != settings.webhook_secret
        ):
            logger.warning("Отклонён запрос вебхука с неверным секретом")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    bot = request.app.state.bot
    dp = request.app.state.dp
    update = Update.model_validate(payload, context={"bot": bot})

    task = asyncio.create_task(dp.feed_update(bot, update))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return JSONResponse({"ok": True})


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    """Service liveness. In polling mode the poller itself is checked too: without
    that, /health answered "ok" even after the bot stopped reading updates."""
    polling_task: asyncio.Task[None] | None = getattr(request.app.state, "polling_task", None)
    polling_alive = polling_task is not None and not polling_task.done()
    healthy = polling_alive or settings.use_webhook

    body = {
        "status": "ok" if healthy else "degraded",
        "mode": settings.run_mode,
        "polling_alive": polling_alive if not settings.use_webhook else None,
        "active_updates": len(_background_tasks),
        "limits": {
            "max_file_size_mb": settings.max_file_size_mb,
            "max_video_duration_sec": settings.max_video_duration_sec,
        },
    }
    return JSONResponse(body, status_code=200 if healthy else 503)


async def require_stats_token(authorization: str | None = Header(default=None)) -> None:
    """Simple Bearer auth for /stats."""
    if not settings.stats_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stats disabled")
    expected = f"Bearer {settings.stats_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/stats", dependencies=[Depends(require_stats_token)])
async def stats() -> dict[str, Any]:
    return await collect_stats()
