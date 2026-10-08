"""Per-user request rate limiting middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, User
from loguru import logger

from app.config import settings
from app.services.rate_limiter import get_rate_limiter

# Commands must not eat the quota - the limit guards against download spam.
EXEMPT_COMMANDS = ("/start", "/help", "/about")

# How often to remind the user about the limit (instead of on every flood message).
NOTICE_COOLDOWN_SEC = 60


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self, limit: int | None = None, window_sec: int | None = None
    ) -> None:
        self.limit = limit or settings.rate_limit_requests
        self.window_sec = window_sec or settings.rate_limit_window_sec

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        if isinstance(event, Message) and (event.text or "").startswith(EXEMPT_COMMANDS):
            return await handler(event, data)

        limiter = get_rate_limiter()
        verdict = await limiter.hit(f"user:{user.id}", self.limit, self.window_sec)
        if verdict.allowed:
            data["rate_limit_remaining"] = verdict.remaining
            return await handler(event, data)

        logger.info("Rate limit для пользователя {}: retry через {} с", user.id, verdict.retry_after_sec)
        if isinstance(event, Message):
            notice = await limiter.hit(f"notice:{user.id}", 1, NOTICE_COOLDOWN_SEC)
            if notice.allowed:
                minutes = max(verdict.retry_after_sec // 60, 0)
                wait = f"{minutes} min" if minutes else f"{verdict.retry_after_sec} s"
                await event.answer(
                    f"⏳ Too many requests: no more than {self.limit} per "
                    f"{self.window_sec // 60} min.\nTry again in {wait}."
                )
        return None
