# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Makefile
# ─────────────────────────────────────────────────

.PHONY: help up down build logs shell migrate test lint clean

help:
	@echo "Samosbor AI Game v2 — Makefile"
	@echo ""
	@echo "  up         — Запустить все сервисы (docker compose up -d)"
	@echo "  down       — Остановить все сервисы"
	@echo "  build      — Пересобрать образ бота"
	@echo "  logs       — Хвост логов бота"
	@echo "  shell      — Bash внутрь контейнера бота"
	@echo "  migrate    — Запустить Alembic миграции"
	@echo "  test       — Запустить тесты"
	@echo "  lint       — Линтинг (ruff)"
	@echo "  clean      — Очистить data/ (сброс БД)"

# ── Docker Compose ───────────────────────────────

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build bot

logs:
	docker compose logs -f bot

shell:
	docker compose exec bot bash

# ── Данные ─────────────────────────────────────

clean:
	@echo "⚠  Удалит все данные БД! (Ctrl+C чтобы отменить)"
	@sleep 3
	rm -rf data/postgres data/temporal-db data/redis

# ── Миграции ───────────────────────────────────

migrate:
	docker compose exec bot alembic upgrade head

# ── Тесты / Линтинг ────────────────────────────

test:
	docker compose exec bot pytest

lint:
	docker compose exec bot ruff check .