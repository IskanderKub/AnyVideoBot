"""Application settings (read from environment variables / .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env.local is read last and wins: secrets and machine-specific overrides
        # live there, out of reach of `cp .env.example .env`.
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    run_mode: str = Field(default="webhook", alias="RUN_MODE")
    telegram_api_base_url: str = Field(default="", alias="TELEGRAM_API_BASE_URL")

    # Group chat triggers: a message shaped like "@link <url>".
    group_triggers: str = Field(default="@link", alias="GROUP_TRIGGERS")
    # Whether to drop updates accumulated while the bot was down.
    # None -> yes for webhook (do not answer a stale backlog), no for polling
    # (in development a message sent before a restart should still arrive).
    drop_pending_updates: bool | None = Field(default=None, alias="DROP_PENDING_UPDATES")

    # --- Storage ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/video_bot.db", alias="DATABASE_URL"
    )
    redis_url: str = Field(default="", alias="REDIS_URL")

    # --- Proxy (for platforms unreachable from the server network) ---
    proxy_url: str = Field(default="", alias="PROXY_URL")
    # Empty -> proxy for every platform; otherwise a comma-separated list.
    proxy_platforms: str = Field(default="", alias="PROXY_PLATFORMS")

    # --- Limits ---
    max_video_duration_sec: int = Field(default=600, alias="MAX_VIDEO_DURATION_SEC")
    max_file_size_mb: int = Field(default=50, alias="MAX_FILE_SIZE_MB")
    rate_limit_requests: int = Field(default=10, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_sec: int = Field(default=300, alias="RATE_LIMIT_WINDOW_SEC")
    max_concurrent_downloads: int = Field(default=4, alias="MAX_CONCURRENT_DOWNLOADS")
    download_timeout_sec: int = Field(default=300, alias="DOWNLOAD_TIMEOUT_SEC")

    # --- Misc ---
    temp_dir: Path = Field(default=Path("/tmp/video_bot"), alias="TEMP_DIR")
    cleanup_interval_sec: int = Field(default=600, alias="CLEANUP_INTERVAL_SEC")
    file_max_age_sec: int = Field(default=1800, alias="FILE_MAX_AGE_SEC")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # Log file: without it a crash or restart leaves no trace of what happened.
    log_file: str = Field(default="logs/bot.log", alias="LOG_FILE")
    stats_token: str = Field(default="", alias="STATS_TOKEN")

    @field_validator("run_mode")
    @classmethod
    def _validate_run_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"webhook", "polling"}:
            raise ValueError("RUN_MODE must be either 'webhook' or 'polling'")
        return value

    @field_validator("drop_pending_updates", mode="before")
    @classmethod
    def _empty_string_means_auto(cls, value: object) -> object:
        """An empty .env value means "let the mode decide", not an error."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("webhook_url", "telegram_api_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @property
    def group_trigger_list(self) -> tuple[str, ...]:
        """Lowercased trigger list, each guaranteed to start with '@'."""
        raw = (t.strip().lower() for t in self.group_triggers.split(","))
        return tuple(t if t.startswith("@") else f"@{t}" for t in raw if t)

    def proxy_for(self, platform: str | None = None) -> str | None:
        """Proxy for a platform: None means go direct."""
        if not self.proxy_url:
            return None
        allowed = {p.strip().lower() for p in self.proxy_platforms.split(",") if p.strip()}
        if allowed and (platform or "").lower() not in allowed:
            return None
        return self.proxy_url

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def webhook_path(self) -> str:
        """Webhook endpoint path: the secret in the URL is the first line of defence."""
        return f"/webhook/{self.webhook_secret or 'telegram'}"

    @property
    def full_webhook_url(self) -> str:
        return f"{self.webhook_url}{self.webhook_path}"

    @property
    def use_webhook(self) -> bool:
        return self.run_mode == "webhook" and bool(self.webhook_url)

    @property
    def should_drop_pending_updates(self) -> bool:
        if self.drop_pending_updates is not None:
            return self.drop_pending_updates
        return self.use_webhook


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
