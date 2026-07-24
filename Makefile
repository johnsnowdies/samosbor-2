# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Makefile
# ─────────────────────────────────────────────────

.PHONY: help up down build logs shell migrate test lint clean load-lore search-lore

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
	@echo "  load-lore  — Загрузить лор в векторную БД (RAG)"
	@echo "  search-lore QUERY=текст — Поиск по лору"
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

# ── RAG ─────────────────────────────────────────

# Запускает ollama, ждёт готовности, грузит лор, останавливает ollama
load-lore:
	docker compose --profile rag up -d ollama
	@echo "⏳ Ожидание Ollama..."
	@for i in $$(seq 1 30); do \
		curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	docker compose exec ollama ollama pull bge-m3 2>/dev/null || true
	docker compose exec -e EMBEDDING_PROVIDER=ollama bot python -m bot.rag.loader
	docker compose stop ollama

# Поиск по лору (ollama нужен только для эмбединга запроса)
search-lore:
	docker compose --profile rag up -d ollama
	@echo "⏳ Ожидание Ollama..."
	@for i in $$(seq 1 30); do \
		curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	docker compose exec -e EMBEDDING_PROVIDER=ollama bot python -m bot.rag.loader --search "$(QUERY)"
	docker compose stop ollama

test:
	docker compose exec bot pytest

lint:
	docker compose exec bot ruff check .