"""The /start, /help and /about commands."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from loguru import logger

from app.config import settings
from app.db.repository import get_or_create_user

router = Router(name="start")

WELCOME = (
    "👋 <b>Hi! I download videos from links.</b>\n\n"
    "Just send me a link and I will send back a ready MP4 file.\n\n"
    "<b>Supported:</b>\n"
    "• YouTube (videos and Shorts)\n"
    "• Instagram (posts and Reels from public accounts)\n"
    "• TikTok\n"
    "• Pinterest (pins with video)\n\n"
    "<b>In a group chat</b> call me with the trigger:\n"
    "<code>{trigger} https://…</code> — or reply <code>{trigger}</code> "
    "to a message with a link.\n\n"
    "<b>Limits:</b>\n"
    "• file size — up to {size} MB\n"
    "• duration — up to {minutes} min\n"
    "• no more than {limit} requests per {window} min\n\n"
    "⚠️ <i>Downloading may violate these platforms' terms of use. "
    "Use it for personal purposes only: respecting copyright is your "
    "responsibility.</i>"
)

HELP = (
    "<b>How to use me</b>\n\n"
    "1. Copy the video link in the app (Share → Copy link).\n"
    "2. Send it to me as a message.\n"
    "3. Wait for the file — usually a few seconds.\n\n"
    "<b>In a group</b> I do not react to every link — call me:\n"
    "• <code>{trigger} https://…</code>\n"
    "• or reply <code>{trigger}</code> to a message with a link.\n\n"
    "<b>If it did not work</b>\n"
    "• “Private account” — only public posts can be downloaded.\n"
    "• “Too large” — try a shorter video (the limit is {size} MB).\n"
    "• “Video unavailable” — check that the link opens in a browser.\n\n"
    "Commands: /start — begin, /help — this help, /about — about the bot."
)

ABOUT = (
    "<b>About</b>\n\n"
    "I download videos from YouTube, Instagram, TikTok and Pinterest "
    "and send them to you as a file in Telegram.\n\n"
    "Your videos are not kept: the file is deleted right after sending.\n"
    "Only the link, the platform and the processing status stay in the logs.\n\n"
    "⚠️ You are responsible for how you use the downloaded content and for "
    "respecting copyright."
)


def _welcome_text() -> str:
    return WELCOME.format(
        trigger=settings.group_trigger_list[0],
        size=settings.max_file_size_mb,
        minutes=settings.max_video_duration_sec // 60,
        limit=settings.rate_limit_requests,
        window=settings.rate_limit_window_sec // 60,
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user:
        await get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code,
        )
        logger.info("/start от пользователя {} (@{})", user.id, user.username)
    await message.answer(_welcome_text())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        HELP.format(size=settings.max_file_size_mb, trigger=settings.group_trigger_list[0])
    )


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(ABOUT)
