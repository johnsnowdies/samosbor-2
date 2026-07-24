# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — LangGraph Graph Assembly
# ─────────────────────────────────────────────────

"""
Сборка графа обработки запроса игрока.

Пути:
  /start → start_game → llm_call → parse → update_state → npc_simulate
  иначе → guardrails → memory → rag → build_prompt → llm_call → parse → update_state → npc_simulate

На каждом шаге проверяется state.error — если есть, обработка прерывается.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from bot.langgraph.nodes.build_prompt import build_prompt
from bot.langgraph.nodes.guardrails import check_guardrails
from bot.langgraph.nodes.llm_call import call_llm
from bot.langgraph.nodes.memory import load_memory
from bot.langgraph.nodes.npc_simulate import simulate_npcs
from bot.langgraph.nodes.parse import parse_response
from bot.langgraph.nodes.rag import retrieve_rag
from bot.langgraph.nodes.start_game import start_game
from bot.langgraph.nodes.update_state import update_state
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)


# ── Conditional edges ────────────────────────────

def is_start_command(state: GameState) -> Literal["start_game", "guardrails"]:
    """Определяет, /start это или обычное сообщение."""
    if state.user_input and state.user_input.strip().lower() == "/start":
        return "start_game"
    return "guardrails"


def has_error(state: GameState) -> Literal["continue", "end"]:
    """Проверяет, есть ли ошибка в state."""
    if state.error is not None:
        logger.info("Graph: ошибка на ноде — завершение: %s", state.error[:100])
        return "end"
    return "continue"


# ── Graph builder ────────────────────────────────

def build_game_graph() -> StateGraph:
    """
    Строит граф обработки запроса.

    Returns:
        Скомпилированный StateGraph
    """
    workflow = StateGraph(GameState)

    # ── Ноды ────────────────────────────────────
    workflow.add_node("start_game", lambda state: _run_with_db(start_game, state))
    workflow.add_node("guardrails", lambda state: check_guardrails(state))
    workflow.add_node("memory", lambda state: _run_with_db(load_memory, state))
    workflow.add_node("rag", lambda state: _run_with_db(retrieve_rag, state))
    workflow.add_node("build_prompt", lambda state: build_prompt(state))
    workflow.add_node("llm_call", lambda state: call_llm(state))
    workflow.add_node("parse", lambda state: parse_response(state))
    workflow.add_node("update_state", lambda state: _run_with_db(update_state, state))
    workflow.add_node("npc_simulate", lambda state: simulate_npcs(state))

    # ── Старт ──────────────────────────────────
    workflow.set_conditional_entry_point(
        is_start_command,
    )

    # ── Путь /start ─────────────────────────────
    workflow.add_edge("start_game", "llm_call")

    # ── Путь обычного сообщения ─────────────────
    workflow.add_edge("guardrails", "memory")
    workflow.add_edge("memory", "rag")
    workflow.add_edge("rag", "build_prompt")
    workflow.add_edge("build_prompt", "llm_call")

    # ── Общий путь после LLM ───────────────────
    workflow.add_conditional_edges(
        "llm_call",
        has_error,
        {"continue": "parse", "end": END},
    )

    workflow.add_conditional_edges(
        "parse",
        has_error,
        {"continue": "update_state", "end": END},
    )

    workflow.add_conditional_edges(
        "update_state",
        has_error,
        {"continue": "npc_simulate", "end": END},
    )

    workflow.add_edge("npc_simulate", END)

    # ── Компиляция ─────────────────────────────
    return workflow.compile()


# ── DB helper ────────────────────────────────────

def _run_with_db(node_func, state: GameState) -> GameState:
    """
    Обёртка для нод, которым нужна DB сессия.

    Создаёт сессию, передаёт в ноду, закрывает.
    """
    from bot.models.base import SessionLocal

    db = SessionLocal()
    try:
        return node_func(state, db)
    finally:
        db.close()


# ── Доступ к графу ─────────────────────────────────

_game_graph: StateGraph | None = None


def get_game_graph():
    """Возвращает скомпилированный граф (ленивая инициализация)."""
    global _game_graph
    if _game_graph is None:
        _game_graph = build_game_graph()
    return _game_graph