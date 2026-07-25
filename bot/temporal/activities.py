# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Temporal Activities
# ─────────────────────────────────────────────────

"""
Activity: run_game_graph

Запускает полный LangGraph граф (13 нод) и возвращает
сериализованный результат для отправки в Telegram.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


# ── Activity ───────────────────────────────────────

@activity.defn
async def run_game_graph(chat_id: int, user_input: str) -> dict[str, Any]:
    """
    Запускает LangGraph граф для одного хода игрока.

    Args:
        chat_id: Telegram chat_id пользователя
        user_input: Текст сообщения / команда

    Returns:
        Сериализованный словарь с результатами:
            success: bool
            text: str | None — нарратив
            actions: list[str] — кнопки действий
            items: list[str] — изменения инвентаря
            quests: list[str] — квесты
            game_over: bool
            location: str | None — новая локация
            image_prompt: str | None
            npc_events: list[dict]
            current_location: str | None
            current_cycle: int
            current_time: str
            error: str | None
    """
    # Запускаем синхронный граф в отдельном потоке
    result = await asyncio.to_thread(_sync_run_graph, chat_id, user_input)
    return result


# ── Синхронный запуск графа ───────────────────────

def _sync_run_graph(chat_id: int, user_input: str) -> dict[str, Any]:
    """
    Синхронно запускает граф и сериализует результат.
    Выполняется внутри asyncio.to_thread.
    """
    from bot.schemas.game import GameState
    from bot.langgraph.graph import get_game_graph

    graph = get_game_graph()
    state = GameState(chat_id=chat_id, user_input=user_input)

    try:
        activity.logger.info("Temporal: запуск графа для chat_id=%s", chat_id)
        
        # Langfuse CallbackHandler для LangGraph
        from bot.utils.langfuse_trace import get_langfuse_handler
        handler = get_langfuse_handler()
        config = {"callbacks": [handler]} if handler else {}
        
        result = graph.invoke(state, config) if config else graph.invoke(state)
        activity.logger.info("Temporal: граф выполнен для chat_id=%s", chat_id)
        return _serialize_result(result)
    except Exception as e:
        activity.logger.error("Temporal: ошибка графа: %s", e)
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ── Сериализация ───────────────────────────────────

def _serialize_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    Превращает сырой результат LangGraph в плоский
    сериализуемый словарь для Temporal и Telegram.

    LangGraph возвращает словарь, где parsed_response — это
    GameAction (Pydantic), extra — dict, и т.д.
    """
    # Базовые поля из state
    base = {
        "success": result.get("error") is None,
        "error": result.get("error"),
        "current_location": result.get("current_location_name"),
        "current_cycle": result.get("current_cycle", 1),
        "current_time": result.get("current_time", "08:00"),
        "game_over": result.get("game_over", False),
    }

    # Поля из parsed_response (GameAction)
    action = result.get("parsed_response")
    if action is not None:
        # action — это GameAction (Pydantic) или dict
        if hasattr(action, "model_dump"):
            action_data = action.model_dump()
        elif isinstance(action, dict):
            action_data = action
        else:
            action_data = {}

        base.update({
            "text": action_data.get("text"),
            "actions": action_data.get("actions", []),
            "items": action_data.get("items", []),
            "quests": action_data.get("quests", []),
            "location": action_data.get("location"),
            "image_prompt": action_data.get("image_prompt"),
            "game_over": bool(action_data.get("game_over", False)),
        })
    else:
        base.update({
            "text": None,
            "actions": [],
            "items": [],
            "quests": [],
            "location": None,
            "image_prompt": None,
        })

    # NPC события из extra
    extra = result.get("extra", {})
    if isinstance(extra, dict):
        base["npc_events"] = extra.get("npc_events", [])
    else:
        base["npc_events"] = []

    return base