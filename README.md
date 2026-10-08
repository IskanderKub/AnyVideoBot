<p align="center">
  <img src="assets/logo.png" alt="AnyVideoBot" width="420">
</p>

<h1 align="center">AnyVideoBot</h1>

<p align="center">
  Send a link to a Telegram bot — get the video back as an MP4 file.
</p>

---

## What it does

Social apps make it hard to keep a video you liked. AnyVideoBot turns a link into a normal
MP4 file you can save, forward or edit.

| Platform | What works |
|---|---|
| **YouTube** | Videos and Shorts |
| **Instagram** | Posts and Reels from public accounts |
| **TikTok** | Videos |
| **Pinterest** | Pins containing video |

No ads, no watermarks, no website to visit. The file is deleted from the server right after
it is sent — nothing is kept.

## How to use it

**In a direct chat** — just send the link:

```
You:  https://www.youtube.com/shorts/xxxxxxxxx
Bot:  ⏳ Processing the link (YouTube)…
Bot:  🎬 video.mp4
```

**In a group chat** the bot stays quiet unless you call it, so it never interrupts a
conversation:

```
@link https://www.tiktok.com/@user/video/123     link in the same message
@link                                             as a reply to someone else's link
@your_bot_name https://…                          a mention also works
```

**Good to know**

- Files up to **50 MB** and videos up to **10 minutes** (both configurable).
- Up to **10 links per 5 minutes** per person.
- Private accounts, stories and personal invite links cannot be downloaded — the bot says so
  in plain words instead of failing silently.

## Run your own

You need [Docker](https://docs.docker.com/get-docker/) and a token from
[@BotFather](https://t.me/BotFather) (`/newbot`, then copy the token).

```bash
git clone <this repo> && cd AnyVideoBot
cp -n .env.example .env                                            # shared settings
printf 'BOT_TOKEN=<your token>\nRUN_MODE=polling\n' > .env.local   # your secret
docker compose up -d
```

That is all — write `/start` to your bot. To watch what it does:
`docker compose logs -f bot`.

> **Keep the token in `.env.local`.** That file is read after `.env` and overrides it, is
> never committed, and survives `cp .env.example .env`.

<details>
<summary><b>Without Docker (for development)</b></summary>

Needs Python 3.11+ and **ffmpeg** (`sudo apt install ffmpeg`), which yt-dlp uses to merge
video with audio.

```bash
make install
cp -n .env.example .env
printf 'BOT_TOKEN=<your token>\nRUN_MODE=polling\n' > .env.local
make migrate
make dev
```

</details>

<details>
<summary><b>Using the bot in a group</b></summary>

1. Add the bot to the chat.
2. Turn privacy mode off at @BotFather: *Bot Settings → Group Privacy → Turn off*.
3. **Remove the bot from the chat and add it again** — the setting only applies on join.

Without step 3 Telegram never delivers `@link` messages to the bot; it warns about this in
the log at startup. A mention (`@your_bot_name <link>`) works either way.

</details>

## Settings

Shared settings go to `.env`, secrets and machine-specific overrides to `.env.local`.

| Variable | Default | What it changes |
|---|---|---|
| `BOT_TOKEN` | — | Token from @BotFather. Required |
| `RUN_MODE` | `webhook` | `polling` needs no domain and is the easy choice |
| `GROUP_TRIGGERS` | `@link` | What people type to call the bot in a group |
| `MAX_FILE_SIZE_MB` | `50` | Telegram's limit for a bot-sent file |
| `MAX_VIDEO_DURATION_SEC` | `600` | Refuse anything longer |
| `RATE_LIMIT_REQUESTS` / `..._WINDOW_SEC` | `10` / `300` | Per-person limit |
| `PROXY_URL` / `PROXY_PLATFORMS` | — | Route some platforms through a proxy |
| `WEBHOOK_URL` / `WEBHOOK_SECRET` | — | Only for `RUN_MODE=webhook` |
| `DATABASE_URL` / `REDIS_URL` | SQLite / in-memory | PostgreSQL and Redis in production |

The rest is documented in [.env.example](.env.example).

## When something does not work

| Symptom | Reason and fix |
|---|---|
| Bot ignores `@link` in a group | Privacy mode is on — see the group section above |
| "Could not connect to TikTok" | The platform is unreachable from your network: set `PROXY_URL=socks5://host:port` and `PROXY_PLATFORMS=tiktok` |
| "The page needs to be reloaded" | yt-dlp is outdated — bump the pin in `requirements.txt` and rebuild |
| "Sign in to confirm you're not a bot" | YouTube blocked the server IP; use a proxy or change the address |
| A personal Pinterest link fails | `/sent/?invite_code=…` links only open for their recipient — ask for a regular pin link |
| No answer at all | `curl localhost:8000/health` — it returns `503` when the bot stopped reading updates |

## Under the hood

Python 3.11+ · aiogram 3 · FastAPI + uvicorn · yt-dlp with instaloader as an Instagram
fallback · SQLAlchemy 2.0 async + alembic · Redis for rate limiting and FSM · Docker.

Downloads run in worker threads behind a semaphore, so the bot keeps answering while files
are being fetched. A video too large for Telegram is retried at a lower resolution before
being refused. Each job gets its own temp directory, removed whether it succeeded or not.

Endpoints: `POST /webhook/{secret}` for Telegram updates, `GET /health` for liveness,
`GET /stats` for usage counts (needs `Authorization: Bearer $STATS_TOKEN`).

Tests: `make test` — platform detection, URL parsing, short-link expansion, error mapping,
rate limiting, cleanup, the group trigger and the HTTP layer.

## Legal note

Downloading content may violate the terms of use of these platforms, and respecting
copyright is up to whoever uses the bot. The same warning is shown in `/start`.
