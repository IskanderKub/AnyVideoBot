"""Wrapper around yt-dlp (primary path) and instaloader (Instagram fallback).

Every blocking call runs in a worker thread via `asyncio.to_thread`, so the event
loop is never blocked. Concurrent downloads are capped by a semaphore.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp
from loguru import logger

from app.config import settings
from app.services.exceptions import (
    DownloadError,
    InviteOnlyLinkError,
    DownloadTimeoutError,
    FileTooLargeError,
    GeoRestrictedError,
    LiveStreamError,
    NoVideoStreamError,
    PrivateContentError,
    RateLimitedError,
    SourceNetworkError,
    UnsupportedPlatformError,
    VideoTooLongError,
    VideoUnavailableError,
)
from app.services.platform_detector import Platform, detect_platform
from app.services.url_resolver import resolve as resolve_short_url

# Quality ladder: if the file exceeds the Telegram limit, retry at a lower resolution.
QUALITY_LADDER: tuple[int, ...] = (1080, 720, 480, 360)

_INSTAGRAM_SHORTCODE_RE = re.compile(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")

# Substrings of yt-dlp error text -> domain exception.
# Order matters: more specific diagnoses are checked first - "sign in to confirm
# you're not a bot", for instance, is an IP block rather than a privacy problem.
_ERROR_PATTERNS: tuple[tuple[re.Pattern[str], type[DownloadError]], ...] = (
    (
        re.compile(
            r"429|too many requests|rate.?limit|captcha|"
            r"confirm you'?re not a bot|sign in to confirm",
            re.I,
        ),
        RateLimitedError,
    ),
    (
        re.compile(
            r"geo.?(block|restrict)|available in your country|"
            r"not available in your (country|region)|blocked it in your country",
            re.I,
        ),
        GeoRestrictedError,
    ),
    (
        re.compile(
            r"private|login required|requires? (a )?login|log in|sign in|"
            r"authenticat|cookies|members.only|subscribers? only",
            re.I,
        ),
        PrivateContentError,
    ),
    (
        re.compile(r"\blive (stream|event|broadcast)|is live now|livestream", re.I),
        LiveStreamError,
    ),
    (
        re.compile(
            r"no video|only images|unable to extract.*video|no formats|no media",
            re.I,
        ),
        NoVideoStreamError,
    ),
    (
        re.compile(
            r"unavailable|removed|deleted|does not exist|not found|404|"
            r"terminated|copyright",
            re.I,
        ),
        VideoUnavailableError,
    ),
    (
        re.compile(
            r"unable to download webpage|ssl|timed out|timeout|"
            r"connection (closed|reset|refused|aborted)|name resolution|"
            r"failed to perform",
            re.I,
        ),
        SourceNetworkError,
    ),
)


class _Cancelled(Exception):
    """Internal signal: the download thread must stop."""


@dataclass(slots=True)
class DownloadResult:
    file_path: Path
    workdir: Path
    platform: Platform
    title: str
    duration_sec: int | None
    file_size_bytes: int
    width: int | None = None
    height: int | None = None
    uploader: str | None = None
    source_url: str | None = None

    def cleanup(self) -> None:
        """Remove the job working directory along with the file."""
        shutil.rmtree(self.workdir, ignore_errors=True)


def _map_ytdlp_error(exc: Exception) -> DownloadError:
    text = str(exc)
    for pattern, error_cls in _ERROR_PATTERNS:
        if pattern.search(text):
            return error_cls(text)
    return DownloadError(text)


def _network_aware_error(
    exc: Exception, platform: Platform, proxy: str | None
) -> DownloadError:
    """Explain a network error concretely: "try later" is useless advice when the
    platform is unreachable from the server network altogether."""
    mapped = _map_ytdlp_error(exc)
    if not isinstance(mapped, SourceNetworkError):
        return mapped

    hint = (
        " Check the proxy."
        if proxy
        else " The platform looks unreachable from the server network — a proxy or VPN is needed."
    )
    mapped.user_message = f"Could not connect to {platform.title}.{hint}"
    return mapped


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


class VideoDownloader:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
        self._temp_root = Path(settings.temp_dir)
        self._temp_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ public

    async def download(self, url: str) -> DownloadResult:
        """Download a video by URL. Raises a DownloadError subclass on failure."""
        platform = detect_platform(url)
        if platform is Platform.UNKNOWN:
            raise UnsupportedPlatformError()

        workdir = self._temp_root / uuid.uuid4().hex
        workdir.mkdir(parents=True, exist_ok=True)
        cancel_event = threading.Event()

        async with self._semaphore:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._run_blocking, url, platform, workdir, cancel_event),
                    timeout=settings.download_timeout_sec,
                )
            except asyncio.TimeoutError:
                # The thread stops at the next progress hook; clean the dir right away.
                cancel_event.set()
                shutil.rmtree(workdir, ignore_errors=True)
                logger.warning("Таймаут скачивания: {}", url)
                raise DownloadTimeoutError(f"timeout for {url}") from None
            except Exception:
                shutil.rmtree(workdir, ignore_errors=True)
                raise

    # ------------------------------------------------------- blocking pipeline

    def _run_blocking(
        self, url: str, platform: Platform, workdir: Path, cancel: threading.Event
    ) -> DownloadResult:
        # Expand short links ourselves: following Pinterest redirects lands yt-dlp
        # on the error page and loses the pin.
        proxy = settings.proxy_for(platform.value)
        if proxy:
            logger.info("{}: используем прокси", platform.title)
        resolved = resolve_short_url(url, proxy=proxy)
        try:
            return self._download_with_ytdlp(resolved.url, platform, workdir, cancel, proxy)
        except (PrivateContentError, VideoUnavailableError, NoVideoStreamError, DownloadError) as exc:
            if resolved.was_invite:
                # The link was shared personally through the service - not public.
                raise InviteOnlyLinkError(str(exc)) from exc
            if platform is not Platform.INSTAGRAM or isinstance(
                exc, (VideoTooLongError, FileTooLargeError, LiveStreamError)
            ):
                raise
            logger.info("yt-dlp не справился с Instagram ({}), пробуем instaloader", type(exc).__name__)
            try:
                return self._download_instagram_fallback(resolved.url, workdir, proxy)
            except DownloadError as fallback_exc:
                # The fallback failed too - report whichever error says more.
                raise fallback_exc if isinstance(fallback_exc, PrivateContentError) else exc

    def _probe(self, url: str, opts: dict[str, Any]) -> dict[str, Any]:
        with yt_dlp.YoutubeDL({**opts, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise VideoUnavailableError(f"no info for {url}")
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise NoVideoStreamError(f"empty playlist {url}")
            info = entries[0]
        return info

    def _download_with_ytdlp(
        self,
        url: str,
        platform: Platform,
        workdir: Path,
        cancel: threading.Event,
        proxy: str | None = None,
    ) -> DownloadResult:
        base_opts = self._base_opts(workdir, cancel, proxy)

        try:
            info = self._probe(url, base_opts)
        except yt_dlp.utils.DownloadError as exc:
            raise _network_aware_error(exc, platform, proxy) from exc

        if info.get("is_live"):
            raise LiveStreamError(f"live stream {url}")

        duration = info.get("duration")
        if duration and int(duration) > settings.max_video_duration_sec:
            raise VideoTooLongError(int(duration), settings.max_video_duration_sec)

        limit = settings.max_file_size_bytes
        approx = info.get("filesize") or info.get("filesize_approx")
        last_size: int | None = int(approx) if approx else None

        for height in QUALITY_LADDER:
            if cancel.is_set():
                raise _Cancelled()
            attempt_dir = workdir / f"h{height}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            opts = {
                **base_opts,
                "format": self._format_selector(height),
                "outtmpl": str(attempt_dir / "%(id)s.%(ext)s"),
                "max_filesize": limit,
            }
            if _has_ffmpeg():
                opts["merge_output_format"] = "mp4"

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    downloaded = ydl.extract_info(url, download=True)
            except _Cancelled:
                raise
            except yt_dlp.utils.DownloadError as exc:
                if "larger than" in str(exc).lower():
                    shutil.rmtree(attempt_dir, ignore_errors=True)
                    continue
                raise _network_aware_error(exc, platform, proxy) from exc

            file_path = self._resolve_file(downloaded, attempt_dir)
            if file_path is None:
                # max_filesize kicked in: yt-dlp skipped an oversized file.
                shutil.rmtree(attempt_dir, ignore_errors=True)
                continue

            size = file_path.stat().st_size
            last_size = size
            if size > limit:
                shutil.rmtree(attempt_dir, ignore_errors=True)
                continue

            meta = downloaded if isinstance(downloaded, dict) else info
            return DownloadResult(
                file_path=file_path,
                workdir=workdir,
                platform=platform,
                title=(meta.get("title") or "video").strip(),
                duration_sec=int(meta.get("duration") or 0) or None,
                file_size_bytes=size,
                width=meta.get("width"),
                height=meta.get("height"),
                uploader=meta.get("uploader") or meta.get("channel"),
                source_url=meta.get("webpage_url") or url,
            )

        raise FileTooLargeError(last_size, limit)

    def _format_selector(self, max_height: int) -> str:
        """Prefer MP4; without ffmpeg take progressive streams only (no merging)."""
        if not _has_ffmpeg():
            return f"b[ext=mp4][height<=?{max_height}]/b[height<=?{max_height}]/b"
        return (
            f"bv*[ext=mp4][height<=?{max_height}]+ba[ext=m4a]/"
            f"b[ext=mp4][height<=?{max_height}]/"
            f"bv*[height<=?{max_height}]+ba/b[height<=?{max_height}]/b"
        )

    def _base_opts(
        self, workdir: Path, cancel: threading.Event, proxy: str | None = None
    ) -> dict[str, Any]:
        def hook(status: dict[str, Any]) -> None:
            if cancel.is_set():
                raise _Cancelled()

        return {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "playlist_items": "1",
            "ignoreerrors": False,
            "nocheckcertificate": False,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "concurrent_fragment_downloads": 4,
            "restrictfilenames": True,
            "paths": {"temp": str(workdir)},
            "progress_hooks": [hook],
            "logger": _YtdlpLogger(),
            **({"proxy": proxy} if proxy else {}),
        }

    @staticmethod
    def _resolve_file(info: Any, attempt_dir: Path) -> Path | None:
        """Locate the downloaded file: first via yt-dlp metadata, then by scanning."""
        if isinstance(info, dict):
            for entry in info.get("requested_downloads") or []:
                path = entry.get("filepath") or entry.get("_filename")
                if path and Path(path).exists():
                    return Path(path)
        candidates = [p for p in attempt_dir.rglob("*") if p.is_file() and not p.name.endswith(".part")]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_size)

    # --------------------------------------------------- instagram fallback

    def _download_instagram_fallback(
        self, url: str, workdir: Path, proxy: str | None = None
    ) -> DownloadResult:
        import instaloader

        match = _INSTAGRAM_SHORTCODE_RE.search(url)
        if not match:
            # /stories/... and profiles are unreachable without authentication.
            raise PrivateContentError(f"unsupported instagram url {url}")
        shortcode = match.group(1)

        loader = instaloader.Instaloader(
            quiet=True,
            # Without this instaloader spends minutes retrying on 401/429 while
            # holding a semaphore slot.
            max_connection_attempts=1,
            request_timeout=30.0,
            download_comments=False,
            save_metadata=False,
            download_geotags=False,
            compress_json=False,
        )
        if proxy:
            loader.context._session.proxies = {"http": proxy, "https": proxy}
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except Exception as exc:  # instaloader raises its own error types
            text = str(exc).lower()
            if "private" in text or "login" in text or "401" in text or "403" in text:
                raise PrivateContentError(str(exc)) from exc
            if "429" in text or "wait" in text or "rate" in text:
                raise RateLimitedError(str(exc)) from exc
            raise VideoUnavailableError(str(exc)) from exc

        if not post.is_video or not post.video_url:
            raise NoVideoStreamError(f"instagram post {shortcode} has no video")

        duration = int(post.video_duration or 0)
        if duration and duration > settings.max_video_duration_sec:
            raise VideoTooLongError(duration, settings.max_video_duration_sec)

        target = workdir / f"{shortcode}.mp4"
        limit = settings.max_file_size_bytes
        size = _stream_to_file(post.video_url, target, limit, proxy)

        return DownloadResult(
            file_path=target,
            workdir=workdir,
            platform=Platform.INSTAGRAM,
            title=(post.caption or "Instagram video").strip().split("\n")[0][:100],
            duration_sec=duration or None,
            file_size_bytes=size,
            uploader=post.owner_username,
            source_url=url,
        )


class _YtdlpLogger:
    """Quiet yt-dlp down: warnings -> debug, errors -> error."""

    def debug(self, msg: str) -> None:
        logger.debug("yt-dlp: {}", msg)

    def info(self, msg: str) -> None:
        logger.debug("yt-dlp: {}", msg)

    def warning(self, msg: str) -> None:
        logger.debug("yt-dlp warning: {}", msg)

    def error(self, msg: str) -> None:
        logger.error("yt-dlp: {}", msg)


def _stream_to_file(
    url: str, target: Path, limit_bytes: int, proxy: str | None = None
) -> int:
    """Streaming download that aborts once the size limit is exceeded."""
    import httpx

    size = 0
    with httpx.stream(
        "GET", url, timeout=60.0, follow_redirects=True, proxy=proxy
    ) as response:
        response.raise_for_status()
        declared = response.headers.get("content-length")
        if declared and int(declared) > limit_bytes:
            raise FileTooLargeError(int(declared), limit_bytes)
        with target.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=1 << 16):
                size += len(chunk)
                if size > limit_bytes:
                    fh.close()
                    target.unlink(missing_ok=True)
                    raise FileTooLargeError(None, limit_bytes)
                fh.write(chunk)
    return size


_downloader: VideoDownloader | None = None


def get_downloader() -> VideoDownloader:
    """Lazy singleton: no filesystem or semaphore work at import time."""
    global _downloader
    if _downloader is None:
        _downloader = VideoDownloader()
    return _downloader
