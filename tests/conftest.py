import os
import sys
from pathlib import Path

# Tests must not touch the real .env or real directories.
os.environ.setdefault("BOT_TOKEN", "123:TEST")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
