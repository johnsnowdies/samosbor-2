# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — FastAPI приложение
# ─────────────────────────────────────────────────

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

# ── Логирование ─────────────────────────────────
logging_level = os.getenv("LOGGING_LEVEL", "INFO")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, logging_level.upper()),
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / Shutdown."""
    logger.info("🚀 Samosbor AI Game v2 — запуск")
    # TODO: инициализация подключений (DB, Redis, Temporal, Langfuse)
    yield
    logger.info("🛑 Samosbor AI Game v2 — остановка")
    # TODO: закрытие подключений


# ── Приложение ──────────────────────────────────
app = FastAPI(
    title="Samosbor AI Game v2",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Health ──────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


# ── Webhook ─────────────────────────────────────
@app.post("/webhook")
async def webhook(request: Request):
    """Приём сообщений от Telegram."""
    # TODO: парсинг Update, проверка баланса, запуск Temporal Workflow
    return JSONResponse(content={"ok": True})


# ── Metrics ─────────────────────────────────────
@app.get("/metrics")
async def metrics():
    """Prometheus-метрики."""
    # TODO: сбор метрик
    return {"status": "ok"}