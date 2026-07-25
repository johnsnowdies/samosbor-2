# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — FastAPI + Telegram Bot
# ─────────────────────────────────────────────────

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

# ── Логирование ─────────────────────────────────
logging_level = os.getenv("LOGGING_LEVEL", "INFO")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, logging_level.upper()),
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ── Глобальные ссылки ───────────────────────────
_temporal_client = None
_temporal_worker_task = None
_telegram_bot = None
_telegram_thread = None


# ── Lifespan ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / Shutdown."""
    global _temporal_client, _temporal_worker_task, _telegram_bot, _telegram_thread

    logger.info("🚀 Samosbor AI Game v2 — запуск")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
        yield
        logger.info("🛑 Остановка")
        return

    # ── Temporal (если доступен) ────────────────
    try:
        from bot.temporal import create_client, start_worker

        _temporal_client = await create_client()
        _temporal_worker_task = asyncio.create_task(start_worker(_temporal_client))
        logger.info("Temporal Worker запущен")
    except Exception as e:
        logger.warning("Temporal недоступен (%s) — игра без оркестрации", e)

    # ── Telegram bot (polling в отдельном потоке) ──
    from bot.telegram_bot import SamosborTelegramBot

    _telegram_bot = SamosborTelegramBot(token)
    if _temporal_client:
        _telegram_bot.set_temporal_client(_temporal_client)

    _telegram_thread = threading.Thread(
        target=_telegram_bot.run,
        name="telegram-bot",
        daemon=True,
    )
    _telegram_thread.start()
    logger.info("Telegram bot запущен (thread=%s)", _telegram_thread.name)

    yield

    logger.info("🛑 Samosbor AI Game v2 — остановка")

    if _temporal_worker_task:
        _temporal_worker_task.cancel()
        try:
            await _temporal_worker_task
        except asyncio.CancelledError:
            pass

    # Telegram bot в daemon-треде — остановится сам


# ── FastAPI приложение ──────────────────────────
app = FastAPI(
    title="Samosbor AI Game v2",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/metrics")
async def metrics():
    return {"status": "ok"}
