import pytest

from app.services.downloader import _map_ytdlp_error
from app.services.exceptions import (
    DownloadError,
    FileTooLargeError,
    GeoRestrictedError,
    LiveStreamError,
    NoVideoStreamError,
    PrivateContentError,
    RateLimitedError,
    SourceNetworkError,
    VideoTooLongError,
    VideoUnavailableError,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ERROR: This account is private", PrivateContentError),
        ("ERROR: Login required to access this content", PrivateContentError),
        ("ERROR: HTTP Error 429: Too Many Requests", RateLimitedError),
        ("ERROR: The uploader has not made this video available in your country", GeoRestrictedError),
        ("ERROR: Video unavailable", VideoUnavailableError),
        ("ERROR: This video has been removed by the uploader", VideoUnavailableError),
        ("ERROR: Unable to extract video url; no formats found", NoVideoStreamError),
        ("ERROR: Sign in to confirm you're not a bot", RateLimitedError),
        ("ERROR: The uploader has blocked it in your country", GeoRestrictedError),
        ("ERROR: This live event will begin soon", LiveStreamError),
        (
            "ERROR: [TikTok] Unable to download webpage: Failed to perform, curl: (35) "
            "BoringSSL SSL_connect: Connection closed abruptly",
            SourceNetworkError,
        ),
        ("ERROR: read operation timed out", SourceNetworkError),
        ("ERROR: something totally unexpected", DownloadError),
    ],
)
def test_error_mapping(text, expected):
    mapped = _map_ytdlp_error(Exception(text))
    assert type(mapped) is expected
    assert mapped.user_message


def test_too_long_message_mentions_limit():
    exc = VideoTooLongError(900, 600)
    assert "10 min" in exc.user_message
    assert "15" in exc.user_message


def test_too_large_message_mentions_limit_in_mb():
    exc = FileTooLargeError(80 * 1024 * 1024, 50 * 1024 * 1024)
    assert "50 MB" in exc.user_message
    assert "80" in exc.user_message


def test_too_large_without_known_size():
    exc = FileTooLargeError(None, 50 * 1024 * 1024)
    assert "50 MB" in exc.user_message
