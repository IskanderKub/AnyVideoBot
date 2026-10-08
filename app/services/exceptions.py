"""Download domain errors carrying ready-made user-facing messages."""

from __future__ import annotations


class DownloadError(Exception):
    """Base error. `user_message` is shown to the user verbatim."""

    user_message = "Could not download the video. Try another link."

    def __init__(self, message: str | None = None, *, user_message: str | None = None):
        super().__init__(message or self.__class__.user_message)
        if user_message:
            self.user_message = user_message


class UnsupportedPlatformError(DownloadError):
    user_message = (
        "This platform is not supported.\n"
        "I can download videos from YouTube, Instagram, TikTok and Pinterest."
    )


class InvalidUrlError(DownloadError):
    user_message = "That does not look like a link. Send a full URL starting with http(s)://"


class PrivateContentError(DownloadError):
    user_message = (
        "The content is closed: a private account, or login is required. "
        "Only public posts can be downloaded."
    )


class VideoUnavailableError(DownloadError):
    user_message = "The video is unavailable: deleted, hidden, or the link is wrong."


class NoVideoStreamError(DownloadError):
    user_message = "There is no video behind this link — looks like photos or text only."


class LiveStreamError(DownloadError):
    user_message = "This is a live stream. Downloading broadcasts is not supported."


class GeoRestrictedError(DownloadError):
    user_message = "The video is not available in the server region (geo block)."


class VideoTooLongError(DownloadError):
    def __init__(self, duration_sec: int, limit_sec: int):
        super().__init__(f"duration {duration_sec}s > limit {limit_sec}s")
        self.user_message = (
            f"The video is too long: {duration_sec // 60} min "
            f"(the limit is {limit_sec // 60} min)."
        )


class FileTooLargeError(DownloadError):
    def __init__(self, size_bytes: int | None, limit_bytes: int):
        super().__init__(f"file {size_bytes} bytes > limit {limit_bytes} bytes")
        limit_mb = limit_bytes // (1024 * 1024)
        actual = (
            f" (about {size_bytes / 1024 / 1024:.0f} MB)" if size_bytes else ""
        )
        self.user_message = (
            f"The video is too large{actual}. The sending limit is {limit_mb} MB."
        )


class DownloadTimeoutError(DownloadError):
    user_message = "The download took too long. Try again later."


class InviteOnlyLinkError(DownloadError):
    """A personal link (Pinterest "sent to you") - does not open anonymously."""

    user_message = (
        "This is a personal invite link: it only opens for its recipient, "
        "so nothing can be downloaded from it.\n"
        "Open the post in the app and copy the regular link "
        "(Share → Copy link)."
    )


class SourceNetworkError(DownloadError):
    """Could not reach the platform: TLS/DNS/timeout on the network side."""

    user_message = (
        "Could not reach the platform (network error). Try again in a minute."
    )


class RateLimitedError(DownloadError):
    """The platform throttled the request (429 / captcha / IP block)."""

    user_message = (
        "The platform has temporarily limited access to the video. Try in a few minutes."
    )
