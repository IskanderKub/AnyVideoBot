"""Short link expansion (no network access)."""

import pytest

from app.services.url_resolver import (
    ResolvedUrl,
    canonicalize_pinterest,
    looks_like_invite,
    resolve,
)

# A real pin.it redirect chain: it ends on the error page, yet carries the pin id.
PIN_IT_CHAIN = [
    "https://pin.it/6FrTE65vi",
    "https://api.pinterest.com/url_shortener/6FrTE65vi/redirect/",
    "https://www.pinterest.ru/pin/914723374340283384/sent/?invite_code=0a0b3c&sender=914723511723971584&sfo=1",
    "https://ru.pinterest.com/?show_error=true",
]


def test_canonicalize_extracts_pin_id_from_chain():
    assert (
        canonicalize_pinterest(PIN_IT_CHAIN)
        == "https://www.pinterest.com/pin/914723374340283384/"
    )


def test_canonicalize_returns_none_without_pin_id():
    assert canonicalize_pinterest(["https://pin.it/x", "https://ru.pinterest.com/?show_error=true"]) is None


def test_invite_link_is_detected():
    assert looks_like_invite(PIN_IT_CHAIN) is True


def test_plain_pin_chain_is_not_invite():
    chain = ["https://pin.it/abc", "https://www.pinterest.com/pin/1136314549764127019/"]
    assert looks_like_invite(chain) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://www.pinterest.com/pin/123/",
        "https://www.tiktok.com/@user/video/123",
        "https://www.instagram.com/reel/abc/",
    ],
)
def test_non_shortener_urls_are_returned_untouched(url, monkeypatch):
    """Ordinary links must not trigger a network request."""

    def fail(*args, **kwargs):
        raise AssertionError("no network request is needed for an ordinary link")

    monkeypatch.setattr("httpx.Client", fail)
    assert resolve(url) == ResolvedUrl(url)


def test_resolve_falls_back_to_original_url_on_network_error(monkeypatch):
    """Network is down - return the original link and let yt-dlp try itself."""

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise OSError("network is unreachable")

    monkeypatch.setattr("httpx.Client", BrokenClient)
    result = resolve("https://pin.it/6FrTE65vi")
    assert result.url == "https://pin.it/6FrTE65vi"
    assert result.redirected is False


class TestProxySelection:
    """PROXY_URL can be limited to a platform list: only TikTok goes via the proxy."""

    def test_no_proxy_configured(self):
        from app.config import Settings

        settings = Settings(BOT_TOKEN="x:y")
        assert settings.proxy_for("tiktok") is None

    def test_proxy_for_all_platforms(self):
        from app.config import Settings

        settings = Settings(BOT_TOKEN="x:y", PROXY_URL="socks5://127.0.0.1:1080")
        assert settings.proxy_for("tiktok") == "socks5://127.0.0.1:1080"
        assert settings.proxy_for("youtube") == "socks5://127.0.0.1:1080"

    def test_proxy_limited_to_listed_platforms(self):
        from app.config import Settings

        settings = Settings(
            BOT_TOKEN="x:y",
            PROXY_URL="socks5://127.0.0.1:1080",
            PROXY_PLATFORMS="tiktok, instagram",
        )
        assert settings.proxy_for("tiktok") == "socks5://127.0.0.1:1080"
        assert settings.proxy_for("instagram") == "socks5://127.0.0.1:1080"
        assert settings.proxy_for("youtube") is None
