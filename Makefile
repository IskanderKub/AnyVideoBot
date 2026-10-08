.PHONY: install run dev test lint docker-up docker-down migrate revision

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

run:  ## production mode (webhook)
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers

dev:  ## local: RUN_MODE=polling in .env, auto-reload
	.venv/bin/uvicorn app.main:app --reload --port 8000

test:
	.venv/bin/python -m pytest

migrate:
	.venv/bin/alembic upgrade head

revision:
	.venv/bin/alembic revision --autogenerate -m "$(m)"

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
