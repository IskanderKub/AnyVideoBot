import pytest

from app.services.platform_detector import Platform, detect_platform, is_supported


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://m.youtube.com/shorts/abc123",
        "https://music.youtube.com/watch?v=abc",
        "https://www.youtube-nocookie.com/embed/abc",
        "HTTPS://WWW.YOUTUBE.COM/watch?v=abc",
    ],
)
def test_youtube(url):
    assert detect_platform(url) is Platform.YOUTUBE


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/p/CxYzAbC1234/",
        "https://instagram.com/reel/CxYzAbC1234/?igshid=1",
        "https://www.instagram.com/tv/CxYzAbC1234/",
        "https://instagr.am/p/CxYzAbC1234/",
    ],
)
def test_instagram(url):
    assert detect_platform(url) is Platform.INSTAGRAM


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@user/video/7123456789012345678",
        "https://vm.tiktok.com/ZMabcdefg/",
        "https://vt.tiktok.com/ZSabcdefg/",
        "https://m.tiktok.com/v/7123456789012345678.html",
    ],
)
def test_tiktok(url):
    assert detect_platform(url) is Platform.TIKTOK


@pytest.mark.parametrize(
    "url",
    [
        "https://www.pinterest.com/pin/1234567890/",
        "https://ru.pinterest.com/pin/1234567890/",
        "https://pinterest.ru/pin/1234567890/",
        "https://pinterest.co.uk/pin/1234567890/",
        "https://pin.it/abcDEF",
    ],
)
def test_pinterest(url):
    assert detect_platform(url) is Platform.PINTEREST


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/123456",
        "https://example.com/video.mp4",
        "not a url at all",
        "",
        "ftp://youtube.com/video",
        # A platform domain in the query must not be taken for the platform itself.
        "https://evil.example/?redirect=https://youtube.com/watch?v=1",
        "https://youtube.com.evil.example/watch?v=1",
        "https://notinstagram.com/p/abc/",
    ],
)
def test_unsupported(url):
    assert detect_platform(url) is Platform.UNKNOWN
    assert is_supported(url) is False


def test_platform_titles():
    assert Platform.YOUTUBE.title == "YouTube"
    assert Platform.TIKTOK.title == "TikTok"
