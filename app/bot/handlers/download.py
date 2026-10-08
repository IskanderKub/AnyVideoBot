"""Main handler: link -> video file.

In a direct chat sending the link is enough. In a group the bot stays silent until
called by a trigger ("@link <url>") or a mention - otherwise it would react to every
message containing a URL.
"""

from __future__ import annotations

import html
import time

from aiogram import F, Router
from aiogram.enums import ChatAction, ChatType
from aiogram.exceptions import TelegramEntityTooLarge, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from loguru import logger

from app.bot.filters import LinkTrigger
from app.config import settings
from app.db.models import DownloadStatus
from app.db.repository import get_or_create_user, log_download_finish, log_download_start
from app.services.cleanup import remove_path
from app.services.downloader import DownloadResult, get_downloader
from app.services.exceptions import DownloadError, FileTooLargeError, UnsupportedPlatformError
from app.services.platform_detector import Platform, detect_platform
from app.utils.validators import extract_url, normalize_url

router = Router(name="download")

IS_PRIVATE = F.chat.type == ChatType.PRIVATE
IS_GROUP = F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})

NO_URL_HINT = (
    "I am waiting for a video link 🙂\n\n"
    "Send a URL from YouTube, Instagram, TikTok or Pinterest.\n"
    "More details — /help"
)

MAX_CAPTION_TITLE = 150


def _group_no_url_hint() -> str:
    trigger = settings.group_trigger_list[0]
    return (
        f"Send the link together with the trigger: <code>{trigger} https://…</code>\n"
        f"Or reply <code>{trigger}</code> to a message with a link."
    )


def _caption(result: DownloadResult) -> str:
    title = html.escape(result.title or "Video")[:MAX_CAPTION_TITLE]
    parts = [f"🎬 <b>{title}</b>", f"📥 Source: {result.platform.title}"]
    if result.uploader:
        parts.append(f"👤 {html.escape(result.uploader)}")
    if result.source_url:
        parts.append(f'<a href="{html.escape(result.source_url, quote=True)}">Open original</a>')
    return "\n".join(parts)


@router.message(IS_PRIVATE, F.text & ~F.text.startswith("/"))
async def handle_private_link(message: Message) -> None:
    """Direct chat: any message with a link is a download request.

    No trigger is needed here, and it does no harm either: "@link <url>" works too.
    If the message carries no link, take it from the one being replied to.
    """
    reply = message.reply_to_message
    url = extract_url(message.text) or extract_url(
        (reply.text or reply.caption) if reply else None
    )
    if not url:
        await message.answer(NO_URL_HINT)
        return
    await process_link(message, url, as_reply=False)


@router.message(IS_GROUP, LinkTrigger())
async def handle_group_trigger(message: Message, url: str | None) -> None:
    """Group: react only to "@link <url>" or a mention of the bot."""
    if url is None:
        await message.reply(_group_no_url_hint())
        return
    await process_link(message, url, as_reply=True)


async def process_link(message: Message, raw_url: str, *, as_reply: bool) -> None:
    """Shared flow: detect the platform, download, send, clean up."""
    tg_user = message.from_user
    url = normalize_url(raw_url)
    platform = detect_platform(url)
    answer = message.reply if as_reply else message.answer

    if platform is Platform.UNKNOWN:
        await answer(UnsupportedPlatformError.user_message)
        return

    user_id = None
    if tg_user:
        user_id = await get_or_create_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language_code=tg_user.language_code,
        )
    download_id = await log_download_start(user_id, url, platform.value)

    status_message = await answer(f"⏳ Processing the link ({platform.title})…")
    started = time.monotonic()
    result: DownloadResult | None = None

    logger.info(
        "Скачивание начато: user={} chat={} platform={} url={}",
        tg_user.id if tg_user else "?",
        message.chat.id,
        platform,
        url,
    )

    try:
        async with ChatActionSender(
            bot=message.bot, chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO
        ):
            result = await get_downloader().download(url)
            elapsed_ms = int((time.monotonic() - started) * 1000)

            send_video = message.reply_video if as_reply else message.answer_video
            await send_video(
                video=FSInputFile(result.file_path, filename=f"{result.platform.value}.mp4"),
                caption=_caption(result),
                duration=result.duration_sec,
                width=result.width,
                height=result.height,
                supports_streaming=True,
            )

        logger.info(
            "Скачивание завершено: platform={} size={:.1f}МБ за {} мс",
            platform,
            result.file_size_bytes / 1024 / 1024,
            elapsed_ms,
        )
        await log_download_finish(
            download_id,
            DownloadStatus.SUCCESS,
            title=result.title,
            duration_sec=result.duration_sec,
            file_size_bytes=result.file_size_bytes,
            elapsed_ms=elapsed_ms,
        )

    except DownloadError as exc:
        logger.warning("Ошибка скачивания ({}): {}", type(exc).__name__, exc)
        await _fail(answer, download_id, started, exc.user_message, str(exc))

    except TelegramEntityTooLarge as exc:
        message_text = FileTooLargeError(
            result.file_size_bytes if result else None, settings.max_file_size_bytes
        ).user_message
        await _fail(answer, download_id, started, message_text, str(exc))

    except TelegramRetryAfter as exc:
        await _fail(
            answer,
            download_id,
            started,
            f"Telegram asks to wait {exc.retry_after} s. Try again a bit later.",
            str(exc),
        )

    except TelegramNetworkError as exc:
        logger.error("Сеть Telegram: {}", exc)
        await _fail(
            answer,
            download_id,
            started,
            "Could not upload the file to Telegram (network problem). Try again.",
            str(exc),
        )

    except Exception as exc:  # unexpected - generic text for the user, trace to the log
        logger.exception("Непредвиденная ошибка при обработке {}: {}", url, exc)
        await _fail(
            answer,
            download_id,
            started,
            "Something went wrong while processing the link. The error is already logged.",
            str(exc),
        )

    finally:
        # Temp files are removed either way - on success and on failure alike.
        if result is not None:
            remove_path(result.workdir)
        await _safe_delete(status_message)


async def _fail(answer, download_id: int | None, started: float, user_text: str, error: str) -> None:
    await log_download_finish(
        download_id,
        DownloadStatus.FAILED,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )
    await answer(f"❌ {user_text}")


async def _safe_delete(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except Exception:  # already deleted or too old - does not matter
        pass
