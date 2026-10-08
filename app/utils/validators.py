"""URL validation and extraction from user messages."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

# A link inside arbitrary text ("check this out https://... neat").
URL_RE = re.compile(r"https?://[^\s<>\"'\\]+", re.IGNORECASE)

# Trailing punctuation that almost always belongs to the sentence, not the URL.
_TRAILING_PUNCTUATION = ".,;:!?)]}»\"'"

MAX_URL_LENGTH = 2048


def extract_url(text: str | None) -> str | None:
    """Return the first valid URL found in the text, or None."""
    if not text:
        return None
    for candidate in URL_RE.findall(text):
        cleaned = candidate.rstrip(_TRAILING_PUNCTUATION)
        if is_valid_url(cleaned):
            return cleaned
    return None


def is_valid_url(url: str | None) -> bool:
    """Basic check: http(s) scheme, non-empty host, sane length."""
    if not url or len(url) > MAX_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname
    if not host or "." not in host:
        return False
    return True


def normalize_url(url: str) -> str:
    """Drop the fragment and lowercase the host."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    return urlunparse(
        (parsed.scheme.lower(), netloc, parsed.path, parsed.params, parsed.query, "")
    )
