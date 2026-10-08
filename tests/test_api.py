"""HTTP layer tests. Lifespan does not run: ASGITransport sends no lifespan events,
so nothing here talks to Telegram or the database."""

import httpx
import pytest

from app.main import app


@pytest.fixture
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_health_reports_limits(client: httpx.AsyncClient, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "run_mode", "webhook")
    monkeypatch.setattr(settings, "webhook_url", "https://example.com")
    async with client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "webhook"
    assert body["limits"]["max_file_size_mb"] > 0


async def test_health_is_degraded_when_polling_is_dead(
    client: httpx.AsyncClient, monkeypatch
):
    """A dead poller means the bot reads no updates - /health must say so."""
    from app.config import settings

    monkeypatch.setattr(settings, "run_mode", "polling")
    monkeypatch.setattr(settings, "webhook_url", "")
    async with client:
        response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["polling_alive"] is False


async def test_webhook_rejects_wrong_secret(client: httpx.AsyncClient):
    async with client:
        response = await client.post("/webhook/wrong-secret", json={"update_id": 1})

    assert response.status_code == 403


async def test_webhook_rejects_wrong_header(client: httpx.AsyncClient):
    from app.config import settings

    async with client:
        response = await client.post(
            f"/webhook/{settings.webhook_secret}",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
        )

    assert response.status_code == 403


async def test_stats_requires_token(client: httpx.AsyncClient, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "stats_token", "s3cret")
    async with client:
        unauthorized = await client.get("/stats")
        wrong = await client.get("/stats", headers={"Authorization": "Bearer nope"})

    assert unauthorized.status_code == 401
    assert wrong.status_code == 401


async def test_stats_disabled_without_token(client: httpx.AsyncClient, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "stats_token", "")
    async with client:
        response = await client.get("/stats")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "run_mode,webhook_url,expected",
    [
        ("webhook", "https://example.com", True),   # prod: do not answer a stale backlog
        ("polling", "", False),                     # dev: a message sent before a restart arrives
    ],
)
def test_drop_pending_updates_default_depends_on_mode(
    run_mode, webhook_url, expected, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "run_mode", run_mode)
    monkeypatch.setattr(settings, "webhook_url", webhook_url)
    monkeypatch.setattr(settings, "drop_pending_updates", None)
    assert settings.should_drop_pending_updates is expected


def test_drop_pending_updates_env_override(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "run_mode", "polling")
    monkeypatch.setattr(settings, "drop_pending_updates", True)
    assert settings.should_drop_pending_updates is True
