# AnyVideoBot

A Telegram bot: send a link, get an MP4 file back.
Supports YouTube (videos, Shorts), Instagram (posts and Reels from public accounts),
TikTok and Pinterest.

In a direct chat, sending the link is enough. In a group the bot answers only when called:

```
@link https://www.youtube.com/shorts/xxxx     link in the message
@link                                          as a reply to a message with a link
@bot_name https://…                            a mention (always works)
```

Built to a written spec: webhook-first architecture, async downloads, per-user rate
limiting, temp-file cleanup and tests.

## Stack

Python 3.11+ · aiogram 3 · FastAPI + uvicorn (webhook) · yt-dlp + instaloader ·
SQLAlchemy 2.0 async + alembic · Redis (rate limiting, FSM) · loguru · Docker

## Running

**ffmpeg** is required (`sudo apt install ffmpeg`) — without it yt-dlp cannot merge
video with audio.

Locally (long polling, no HTTPS domain needed):

```bash
make install
cp -n .env.example .env                                     # shared settings
printf 'BOT_TOKEN=<your token>\nRUN_MODE=polling\n' > .env.local   # secrets
make migrate
make dev
```

`.env.local` is read after `.env` and overrides it. Keep the token there and nowhere else:
that file is never committed and `cp .env.example .env` cannot wipe it.

In Docker (bot + postgres + redis):

```bash
cp -n .env.example .env
printf 'BOT_TOKEN=<your token>\nRUN_MODE=polling\n' > .env.local
make docker-up
```

`RUN_MODE=polling` works in Docker as is. `RUN_MODE=webhook` needs a public HTTPS address:
fill in `WEBHOOK_URL` and `WEBHOOK_SECRET` and put an HTTPS proxy (nginx/Caddy/Traefik) in
front of the container — the webhook is then set automatically to
`${WEBHOOK_URL}/webhook/${WEBHOOK_SECRET}`. With `WEBHOOK_URL=https://example.com`
Telegram will never reach the bot.

## Settings (.env)

| Variable | Default | Purpose |
|---|---|---|
| `BOT_TOKEN` | — | Token from @BotFather (required, keep it in `.env.local`) |
| `RUN_MODE` | `webhook` | `polling` for development |
| `WEBHOOK_URL` / `WEBHOOK_SECRET` | — | Service address and webhook secret |
| `DATABASE_URL` | SQLite in `./data` | Connection string (PostgreSQL in production) |
| `REDIS_URL` | — | Shared rate limiting and FSM; empty → in-memory |
| `GROUP_TRIGGERS` | `@link` | Group triggers, comma-separated |
| `PROXY_URL` / `PROXY_PLATFORMS` | — | Proxy (for everything, or for listed platforms) |
| `MAX_FILE_SIZE_MB` | `50` | Telegram limit for sending a file |
| `MAX_VIDEO_DURATION_SEC` | `600` | Duration limit |
| `RATE_LIMIT_REQUESTS` / `..._WINDOW_SEC` | `10` / `300` | 10 requests per 5 minutes per user |
| `TELEGRAM_API_BASE_URL` | — | Local Bot API server: files up to 2 GB |
| `LOG_LEVEL` / `LOG_FILE` | `INFO` / `logs/bot.log` | Logging |

The remaining parameters are documented in [.env.example](.env.example).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/webhook/{secret_token}` | Telegram updates (answers 200 at once, handles in background) |
| GET | `/health` | Liveness; in polling mode returns `503` if the poller died |
| GET | `/stats` | Usage stats, requires `Authorization: Bearer $STATS_TOKEN` |

## Operations

- **Groups:** turn privacy mode off at @BotFather (*Bot Settings → Group Privacy → Turn off*)
  and **re-add the bot to the chat** — otherwise Telegram does not deliver `@link` messages
  to it. The bot warns about privacy mode in the log at startup.
- **Update yt-dlp regularly** — platforms keep changing their defences, and an old version
  fails with errors like "The page needs to be reloaded".
- **A platform unreachable from the server network** (common with TikTok: DNS resolves, TLS
  does not) — add a proxy: `PROXY_URL=socks5://host:port`, `PROXY_PLATFORMS=tiktok`.
- **YouTube may block the server IP** ("Sign in to confirm you're not a bot") — rotating the
  IP or using a proxy helps; the bot recognises such answers and reports a temporary limit.
- **Instagram:** public posts and Reels only; Stories require authentication.
- Short links (`pin.it`, `vt.tiktok.com`) are expanded to their canonical address.
  Pinterest personal invite links (`/sent/?invite_code=…`) do not open publicly — the bot
  asks for a regular pin link instead.
- The temp directory must be writable by the container user; the bot refuses to start
  otherwise. A tmpfs mount needs `mode: 01777`, as set in `docker-compose.yml`.

## Tests

```bash
make test
```

Covering platform detection, URL parsing, short-link expansion, proxy selection, mapping of
yt-dlp errors to user messages, the rate limiter, temp-file cleanup, the group trigger and
the HTTP layer.

## Legal note

Downloading content may violate the platforms' terms of use. Respecting copyright is the
responsibility of whoever uses the bot — the warning is shown in `/start`.
