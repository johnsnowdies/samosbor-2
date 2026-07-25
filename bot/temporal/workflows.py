# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Temporal Workflows
# ─────────────────────────────────────────────────

"""
Workflow: GameSessionWorkflow

Оркестрирует один ход игрока:
  1. Запускает LangGraph граф (все 13 нод)
  2. Возвращает результат для отправки в Telegram

Запускается из FastAPI webhook.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class GameSessionWorkflow:
    """
    Workflow обработки одного сообщения игрока.

    Выполняет одну активность — run_game_graph, которая запускает
    полный LangGraph граф (guardrails → memory → RAG → LLM → parse
    → update_state → fact_check → npc_simulate).

    Retry: 3 попытки с exponential backoff.
    """

    @workflow.run
    async def run(self, chat_id: int, user_input: str) -> dict:
        result = await workflow.execute_activity(
            "run_game_graph",
            args=[chat_id, user_input],
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=2),
            ),
        )
        return result