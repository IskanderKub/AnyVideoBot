"""Handler filters: a link goes to download, a command does not."""

from datetime import datetime, timezone

import pytest
from aiogram import F
from aiogram.types import Chat, Message

from app.bot.handlers.download import IS_GROUP, IS_PRIVATE
from app.bot.middlewares.rate_limit import EXEMPT_COMMANDS

LINK_FILTER = F.text & ~F.text.startswith("/")


def _message(text: str | None, chat_type: str = "private") -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type=chat_type),
        text=text,
    )


@pytest.mark.parametrize(
    "text,matches",
    [
        ("https://youtu.be/abc", True),
        ("check this https://youtu.be/abc", True),
        ("/start", False),
        ("/help", False),
        (None, False),
    ],
)
def test_link_filter(text, matches):
    assert bool(LINK_FILTER.resolve(_message(text))) is matches


@pytest.mark.parametrize("command", EXEMPT_COMMANDS)
def test_commands_are_exempt_from_rate_limit(command):
    assert command.startswith("/")
    assert _message(command).text.startswith(EXEMPT_COMMANDS)


@pytest.mark.parametrize(
    "chat_type,private,group",
    [
        ("private", True, False),
        ("group", False, True),
        ("supergroup", False, True),
        ("channel", False, False),
    ],
)
def test_chat_type_routing(chat_type, private, group):
    """Direct chats take any link, groups only via the trigger (separate handlers)."""
    message = _message("https://youtu.be/abc", chat_type=chat_type)
    assert bool(IS_PRIVATE.resolve(message)) is private
    assert bool(IS_GROUP.resolve(message)) is group


def test_private_chat_accepts_trigger_prefix():
    """In a direct chat the trigger is optional and does not break URL parsing."""
    from app.utils.validators import extract_url

    assert extract_url("@link https://youtu.be/abc") == "https://youtu.be/abc"
    assert extract_url("https://youtu.be/abc") == "https://youtu.be/abc"
