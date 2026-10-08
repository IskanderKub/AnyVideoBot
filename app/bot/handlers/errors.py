"""Global catch-all for unhandled update errors."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import ErrorEvent
from loguru import logger

router = Router(name="errors")

FALLBACK_TEXT = "❌ An internal error occurred. Try again in a minute."


@router.errors()
async def on_unhandled_error(event: ErrorEvent) -> bool:
    """Log the trace and try to answer the user. True = error handled."""
    logger.opt(exception=event.exception).error(
        "Необработанная ошибка при обработке апдейта {}", event.update.update_id
    )

    message = event.update.message or (
        event.update.callback_query.message if event.update.callback_query else None
    )
    if message is not None:
        try:
            await message.answer(FALLBACK_TEXT)
        except Exception:
            logger.warning("Не удалось отправить сообщение об ошибке пользователю")
    return True
