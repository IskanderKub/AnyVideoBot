"""Handler filters."""

from __future__ import annotations

import re
from functools import lru_cache

from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.config import settings
from app.utils.validators import extract_url


@lru_cache(maxsize=32)
def _trigger_pattern(triggers: tuple[str, ...]) -> re.Pattern[str]:
    """Trigger as a standalone word: '@link' matches, '@linkedin' does not."""
    alternatives = "|".join(re.escape(trigger) for trigger in triggers)
    return re.compile(rf"(?<![\w@])(?:{alternatives})(?![\w])", re.IGNORECASE)


def _text_of(message: Message | None) -> str:
    if message is None:
        return ""
    return message.text or message.caption or ""


class LinkTrigger(BaseFilter):
    """Catches chat messages shaped like "@link <url>".

    Also fires on a mention of the bot itself (@bot_name), which is the only form
    that works while privacy mode is on. The URL is taken from the message, and if
    there is none, from the message being replied to.

    The handler receives `url`: None means "trigger matched but no URL".
    """

    async def __call__(self, message: Message, bot: Bot) -> bool | dict[str, str | None]:
        text = _text_of(message)
        if not text:
            return False

        triggers = settings.group_trigger_list
        me = await bot.me()
        if me.username:
            triggers = (*triggers, f"@{me.username.lower()}")

        match = _trigger_pattern(triggers).search(text)
        if not match:
            return False

        # Look for a URL in the message itself first (trigger text excluded),
        # then in the message being replied to.
        without_trigger = text[: match.start()] + " " + text[match.end() :]
        url = extract_url(without_trigger) or extract_url(_text_of(message.reply_to_message))
        return {"url": url}
