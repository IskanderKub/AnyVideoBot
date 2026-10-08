"""The group chat trigger: "@link <url>"."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from aiogram.types import Chat, Message

from app.bot.filters import LinkTrigger


class FakeBot:
    """aiogram caches bot.me(); the filter only needs the username."""

    def __init__(self, username: str = "anyvideo_bot") -> None:
        self._me = SimpleNamespace(username=username)

    async def me(self):
        return self._me


def _message(text: str | None, reply_text: str | None = None) -> Message:
    reply = (
        Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=-100, type="supergroup"),
            text=reply_text,
        )
        if reply_text is not None
        else None
    )
    return Message(
        message_id=2,
        date=datetime.now(timezone.utc),
        chat=Chat(id=-100, type="supergroup"),
        text=text,
        reply_to_message=reply,
    )


@pytest.mark.parametrize(
    "text,expected_url",
    [
        ("@link https://youtu.be/abc", "https://youtu.be/abc"),
        ("@LINK https://youtu.be/abc", "https://youtu.be/abc"),
        ("team, take a look @link https://youtu.be/abc", "https://youtu.be/abc"),
        ("@link https://youtu.be/abc — funny", "https://youtu.be/abc"),
        ("@anyvideo_bot https://youtu.be/abc", "https://youtu.be/abc"),
    ],
)
async def test_trigger_extracts_url(text, expected_url):
    result = await LinkTrigger()(_message(text), FakeBot())
    assert result == {"url": expected_url}


async def test_trigger_takes_url_from_reply():
    message = _message("@link", reply_text="look at this https://vm.tiktok.com/ZM1/")
    assert await LinkTrigger()(message, FakeBot()) == {"url": "https://vm.tiktok.com/ZM1/"}


async def test_trigger_prefers_url_from_own_text():
    message = _message("@link https://youtu.be/own", reply_text="https://youtu.be/other")
    assert await LinkTrigger()(message, FakeBot()) == {"url": "https://youtu.be/own"}


async def test_trigger_without_any_url_is_matched_with_none():
    assert await LinkTrigger()(_message("@link"), FakeBot()) == {"url": None}


@pytest.mark.parametrize(
    "text",
    [
        "https://youtu.be/abc",           # a link without the trigger - bot stays silent
        "discussing @linkedin openings",  # part of another word
        "write to me@link.ru",            # an email address
        "link https://youtu.be/abc",      # no @
        "",
        None,
    ],
)
async def test_no_trigger_no_match(text):
    assert await LinkTrigger()(_message(text), FakeBot()) is False


async def test_custom_trigger_from_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "group_triggers", "@video")
    assert await LinkTrigger()(_message("@video https://youtu.be/x"), FakeBot()) == {
        "url": "https://youtu.be/x"
    }
    assert await LinkTrigger()(_message("@link https://youtu.be/x"), FakeBot()) is False
