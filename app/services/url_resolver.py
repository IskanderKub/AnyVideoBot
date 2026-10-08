"""Expanding short links to their canonical address.

yt-dlp follows redirects itself, but that breaks on Pinterest: pin.it lands on
the `?show_error=true` service page and the extractor sees "Unsupported URL"
instead of a pin. So short links are expanded up front with our own client and
normalised - using the pin id taken from the redirect chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from loguru import logger

# Shortener hosts that have to be expanded to the real address.
SHORTENER_HOSTS = frozenset({"pin.it", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"})

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_PIN_ID_RE = re.compile(r"/pin/(\d+)")
# Markers of a personal share: such an address only opens for the recipient.
_INVITE_MARKERS = ("invite_code=", "/sent/", "sender=")
_PINTEREST_ERROR_MARKER = "show_error=true"

RESOLVE_TIMEOUT_SEC = 20.0


@dataclass(slots=True)
class ResolvedUrl:
    url: str
    was_invite: bool = False
    redirected: bool = False


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def canonicalize_pinterest(chain: list[str]) -> str | None:
    """Build the canonical pin address from an id found in the redirect chain.

    A /pin/<id>/sent/?invite_code=... link never reaches the pin, but it does carry
    the id - which is enough to build the regular address.
    """
    for url in chain:
        match = _PIN_ID_RE.search(url)
        if match:
            return f"https://www.pinterest.com/pin/{match.group(1)}/"
    return None


def looks_like_invite(chain: list[str]) -> bool:
    return any(marker in url for url in chain for marker in _INVITE_MARKERS)


def resolve(url: str, proxy: str | None = None) -> ResolvedUrl:
    """Expand a short link. On any network error return the original one:
    let yt-dlp try by itself, this is no reason to fail."""
    if _host(url) not in SHORTENER_HOSTS:
        return ResolvedUrl(url)

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=RESOLVE_TIMEOUT_SEC,
            proxy=proxy,
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"},
        ) as client:
            response = client.get(url)
    except Exception as exc:
        logger.warning("Не удалось развернуть короткую ссылку {}: {}", url, exc)
        return ResolvedUrl(url)

    chain = [str(step.url) for step in response.history] + [str(response.url)]
    final = str(response.url)
    invite = looks_like_invite(chain)

    # Pinterest bounced us to the error page - take the pin id from the chain.
    if _PINTEREST_ERROR_MARKER in final or "/pin/" not in final:
        canonical = canonicalize_pinterest(chain)
        if canonical:
            logger.info("Короткая ссылка развёрнута до {}", canonical)
            return ResolvedUrl(canonical, was_invite=invite, redirected=True)

    if final != url:
        logger.info("Короткая ссылка развёрнута до {}", final)
    return ResolvedUrl(final, was_invite=invite, redirected=final != url)
