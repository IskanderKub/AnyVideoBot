"""Bot and Dispatcher construction, router and middleware wiring."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from loguru import logger

from app.bot.handlers import download, errors, start
from app.bot.middlewares.logging import IncomingLogMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.config import settings

BOT_COMMANDS = [
    BotCommand(command="start", description="Get started"),
    BotCommand(command="help", description="How to use the bot"),
    BotCommand(command="about", description="About the bot and its limits"),
]


def _build_storage() -> BaseStorage:
    """FSM state in Redis when available: the process must stay stateless."""
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        logger.info("FSM storage: Redis")
        return RedisStorage.from_url(settings.redis_url)
    logger.warning("FSM storage: MemoryStorage (REDIS_URL не задан)")
    return MemoryStorage()


def create_bot() -> Bot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set - the bot cannot start")

    session = None
    if settings.telegram_api_base_url:
        # A local Bot API server lifts the 50 MB limit (up to 2 GB).
        api = TelegramAPIServer.from_base(settings.telegram_api_base_url, is_local=True)
        session = AiohttpSession(api=api)
        logger.info("Используется локальный Bot API сервер: {}", settings.telegram_api_base_url)

    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=_build_storage())

    # Order matters: log before every check, or filtered-out events stay invisible.
    incoming_log = IncomingLogMiddleware()
    dp.message.middleware(incoming_log)
    dp.callback_query.middleware(incoming_log)

    rate_limit = RateLimitMiddleware()
    dp.message.middleware(rate_limit)
    dp.callback_query.middleware(rate_limit)

    dp.include_router(start.router)
    dp.include_router(download.router)
    dp.include_router(errors.router)

    logger.info("Dispatcher собран: роутеры start, download, errors")
    return dp


async def setup_bot_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception as exc:
        logger.warning("Не удалось установить команды бота: {}", exc)
