"""Platform detection by URL."""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlparse

from app.utils.validators import is_valid_url


class Platform(StrEnum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"
    UNKNOWN = "unknown"

    @property
    def title(self) -> str:
        return _TITLES[self]


_TITLES: dict[Platform, str] = {
    Platform.YOUTUBE: "YouTube",
    Platform.INSTAGRAM: "Instagram",
    Platform.TIKTOK: "TikTok",
    Platform.PINTEREST: "Pinterest",
    Platform.UNKNOWN: "Unknown source",
}

# Patterns match the HOST (minus www.), not the whole URL string, so
# "https://evil.com/?u=youtube.com" is not taken for YouTube.
_HOST_PATTERNS: tuple[tuple[Platform, re.Pattern[str]], ...] = (
    (
        Platform.YOUTUBE,
        re.compile(r"^((m|music|gaming)\.)?youtube(-nocookie)?\.com$|^youtu\.be$"),
    ),
    (
        Platform.INSTAGRAM,
        re.compile(r"^(m\.)?instagram\.com$|^instagr\.am$"),
    ),
    (
        Platform.TIKTOK,
        re.compile(r"^((m|vm|vt|www)\.)?tiktok\.com$"),
    ),
    (
        # pinterest.com, pinterest.ru, pinterest.co.uk, ru.pinterest.com, pin.it
        Platform.PINTEREST,
        re.compile(r"^([a-z]{2}\.)?pinterest\.[a-z]{2,3}(\.[a-z]{2})?$|^pin\.it$"),
    ),
)

SUPPORTED_PLATFORMS: tuple[Platform, ...] = (
    Platform.YOUTUBE,
    Platform.INSTAGRAM,
    Platform.TIKTOK,
    Platform.PINTEREST,
)


def _hostname(url: str) -> str | None:
    try:
        host = urlparse(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def detect_platform(url: str) -> Platform:
    """Return the platform for a URL, or Platform.UNKNOWN."""
    if not is_valid_url(url):
        return Platform.UNKNOWN
    host = _hostname(url)
    if not host:
        return Platform.UNKNOWN
    for platform, pattern in _HOST_PATTERNS:
        if pattern.match(host):
            return platform
    return Platform.UNKNOWN


def is_supported(url: str) -> bool:
    return detect_platform(url) is not Platform.UNKNOWN
