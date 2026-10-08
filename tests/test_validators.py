import pytest

from app.utils.validators import extract_url, is_valid_url, normalize_url


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://youtu.be/abc", "https://youtu.be/abc"),
        ("check this out https://youtu.be/abc neat", "https://youtu.be/abc"),
        ("Link: https://www.tiktok.com/@u/video/1.", "https://www.tiktok.com/@u/video/1"),
        ("(https://pin.it/abc)", "https://pin.it/abc"),
        ("no link here at all", None),
        # Non-ASCII text around the URL must not break extraction.
        ("смотри это https://youtu.be/abc круто", "https://youtu.be/abc"),
        ("", None),
        (None, None),
        ("www.youtube.com/watch?v=1", None),  # no scheme - not a URL
    ],
)
def test_extract_url(text, expected):
    assert extract_url(text) == expected


def test_extract_url_returns_first():
    text = "https://youtu.be/one and also https://youtu.be/two"
    assert extract_url(text) == "https://youtu.be/one"


@pytest.mark.parametrize(
    "url,valid",
    [
        ("https://youtube.com/watch?v=1", True),
        ("http://youtube.com", True),
        ("ftp://youtube.com", False),
        ("https://localhost", False),  # host without a dot
        ("javascript:alert(1)", False),
        ("", False),
        (None, False),
        ("https://youtube.com/" + "a" * 3000, False),  # too long
    ],
)
def test_is_valid_url(url, valid):
    assert is_valid_url(url) is valid


def test_normalize_url_drops_fragment_and_lowercases_host():
    assert (
        normalize_url("HTTPS://WWW.YouTube.com/watch?v=1#t=30")
        == "https://www.youtube.com/watch?v=1"
    )
