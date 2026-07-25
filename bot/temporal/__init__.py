# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Temporal Client + Worker
# ─────────────────────────────────────────────────

"""
Temporal integration for game session orchestration.

Usage:
    from bot.temporal import create_client, start_worker

    client = await create_client()
    handle = await client.start_workflow(
        "GameSessionWorkflow",
        args=[chat_id, user_input],
        id=f"game-{chat_id}-{uuid4()}",
        task_queue="game-tasks",
    )
    result = await handle.get_result()
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "temporal:7233")
TASK_QUEUE = "game-tasks"


async def create_client() -> Client:
    """Создаёт подключение к Temporal Server."""
    logger.info("Temporal: подключение к %s", TEMPORAL_HOST)
    client = await Client.connect(TEMPORAL_HOST)
    logger.info("Temporal: подключено")
    return client


async def start_worker(client: Client) -> Worker:
    """Запускает Worker для обработки активностей.

    Вызывается при старте FastAPI (lifespan).
    """
    from bot.temporal.activities import run_game_graph
    from bot.temporal.workflows import GameSessionWorkflow

    worker = Worker(
        client=client,
        task_queue=TASK_QUEUE,
        workflows=[GameSessionWorkflow],
        activities=[run_game_graph],
    )

    logger.info("Temporal: Worker запущен (task_queue=%s)", TASK_QUEUE)
    await worker.run()
    return worker