"""Incoming update logging.

Registered as the very first middleware - ahead of rate limiting and filters. It
exists so the log tells "the message never reached the bot" apart from "it arrived
and was filtered out".
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, User
from loguru import logger


class IncomingLogMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if isinstance(event, Message):
            logger.info(
                "Входящее сообщение: chat={} ({}) от {} (@{}): {!r}",
                event.chat.id,
                event.chat.type,
                user.id if user else "?",
                user.username if user else "?",
                (event.text or event.caption or "<без текста>")[:80],
            )
        return await handler(event, data)
