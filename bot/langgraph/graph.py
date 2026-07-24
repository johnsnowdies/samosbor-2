# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — LangGraph Graph Assembly
# ─────────────────────────────────────────────────

"""
Сборка графа обработки запроса игрока.

## Пути

### /start:
  start_game → generate_world → build_prompt → llm_call → parse
  → update_state → fact_check → npc_simulate

### Обычное сообщение:
  guardrails → validate_action → memory → rag → build_prompt → llm_call
  → parse → update_state → [если переместился] → generate_locations
  → fact_check → npc_simulate

На каждом шаге проверяется state.error — при ошибке обработка прерывается.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from bot.langgraph.nodes.build_prompt import build_prompt
from bot.langgraph.nodes.fact_check import fact_check
from bot.langgraph.nodes.generate_locations import generate_locations
from bot.langgraph.nodes.generate_world import generate_world
from bot.langgraph.nodes.guardrails import check_guardrails
from bot.langgraph.nodes.llm_call import call_llm
from bot.langgraph.nodes.memory import load_memory
from bot.langgraph.nodes.npc_simulate import simulate_npcs
from bot.langgraph.nodes.parse import parse_response
from bot.langgraph.nodes.rag import retrieve_rag
from bot.langgraph.nodes.start_game import start_game
from bot.langgraph.nodes.update_state import update_state
from bot.langgraph.nodes.validate_action import validate_action
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)


# ── Conditional edges ────────────────────────────

def is_start_command(state: GameState) -> str:
    """Определяет, /start это или обычное сообщение."""
    if state.user_input and state.user_input.strip().lower() == "/start":
        return "start_game"
    return "guardrails"


def route_after_generate_world(state: GameState) -> str:
    """После генерации мира — в build_prompt или END при ошибке."""
    if state.error is not None:
        return END
    return "build_prompt"


def route_after_guardrails(state: GameState) -> str:
    if state.error is not None:
        return END
    return "validate_action"


def route_after_validate(state: GameState) -> str:
    if state.error is not None:
        return END
    return "memory"


def route_after_build_prompt(state: GameState) -> str:
    if state.error is not None:
        return END
    return "llm_call"


def route_after_llm(state: GameState) -> str:
    if state.error is not None:
        return END
    return "parse"


def route_after_parse(state: GameState) -> str:
    if state.error is not None:
        return END
    return "update_state"


def route_after_update(state: GameState) -> str:
    if state.error is not None:
        return END
    if state.location_changed and state.current_location_id is not None:
        return "generate_locations"
    return "fact_check"


def route_after_gen_locations(state: GameState) -> str:
    if state.error is not None:
        return END
    return "fact_check"


def route_after_fact_check(state: GameState) -> str:
    if state.error is not None:
        return END
    return "npc_simulate"


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
    workflow.add_node("generate_world", lambda state: _run_with_db(generate_world, state))
    workflow.add_node("guardrails", lambda state: check_guardrails(state))
    workflow.add_node("validate_action", lambda state: validate_action(state))
    workflow.add_node("memory", lambda state: _run_with_db(load_memory, state))
    workflow.add_node("rag", lambda state: _run_with_db(retrieve_rag, state))
    workflow.add_node("build_prompt", lambda state: build_prompt(state))
    workflow.add_node("llm_call", lambda state: call_llm(state))
    workflow.add_node("parse", lambda state: parse_response(state))
    workflow.add_node("update_state", lambda state: _run_with_db(update_state, state))
    workflow.add_node("generate_locations", lambda state: _run_with_db(generate_locations, state))
    workflow.add_node("fact_check", lambda state: _run_with_db(fact_check, state))
    workflow.add_node("npc_simulate", lambda state: simulate_npcs(state))

    # ── Старт ──────────────────────────────────
    workflow.set_conditional_entry_point(is_start_command)

    # ── Путь /start ─────────────────────────────
    workflow.add_edge("start_game", "generate_world")
    workflow.add_conditional_edges("generate_world", route_after_generate_world)

    # ── Путь обычного сообщения ─────────────────
    workflow.add_conditional_edges("guardrails", route_after_guardrails)
    workflow.add_conditional_edges("validate_action", route_after_validate)
    workflow.add_edge("memory", "rag")
    workflow.add_edge("rag", "build_prompt")

    # ── Общий путь ─────────────────────────────
    workflow.add_conditional_edges("build_prompt", route_after_build_prompt)
    workflow.add_conditional_edges("llm_call", route_after_llm)
    workflow.add_conditional_edges("parse", route_after_parse)
    workflow.add_conditional_edges("update_state", route_after_update)
    workflow.add_conditional_edges("generate_locations", route_after_gen_locations)
    workflow.add_conditional_edges("fact_check", route_after_fact_check)
    workflow.add_edge("npc_simulate", END)

    return workflow.compile()


# ── DB helper ────────────────────────────────────

def _run_with_db(node_func, state: GameState) -> GameState:
    """Обёртка для нод, которым нужна DB сессия."""
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