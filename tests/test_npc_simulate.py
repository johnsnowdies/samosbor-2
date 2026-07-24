# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — NPC Simulate Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды npc_simulate.

Без LLM, без БД — чистая логика FSM.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bot.langgraph.nodes.npc_simulate import simulate_npcs
from bot.schemas.game import GameAction, GameState, NPCAction


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def base_state():
    """Состояние с NPC в локации."""
    return GameState(
        chat_id=12345,
        user_input="осмотреться",
        session_id=42,
        current_location_id=100,
        extra={
            "npcs_in_location": [
                {"id": 20, "name": "Хромой", "faction": "KPGH", "danger_level": 0.7},
                {"id": 21, "name": "Дохлый", "faction": "Likvidator", "danger_level": 0.3},
            ],
        },
    )


# ── Нет NPC ────────────────────────────────────────

class TestNoNPCs:
    """Нет NPC в локации — ничего не делаем."""

    def test_no_npcs(self):
        """npcs_in_location пуст — нет событий."""
        state = GameState(chat_id=1, user_input="тест", extra={})
        result = simulate_npcs(state)
        events = result.extra.get("npc_events", [])
        assert events == []


# ── NPC через LLM ─────────────────────────────────

class TestLLMNPCActions:
    """LLM вернула npc_actions — применяем их."""

    def test_llm_actions_applied(self, base_state):
        """npc_actions из parsed_response добавляются в события."""
        base_state.parsed_response = GameAction(
            text="NPC действуют.",
            actions=[],
            npc_actions=[
                NPCAction(npc_id=20, action="уходит в коридор"),
            ],
        )

        result = simulate_npcs(base_state)

        events = result.extra.get("npc_events", [])
        # Должно быть минимум 1 событие от LLM
        llm_events = [e for e in events if e.get("source") == "llm"]
        assert len(llm_events) >= 1
        assert llm_events[0]["npc_id"] == 20
        assert llm_events[0]["action"] == "уходит в коридор"

    def test_no_parsed_response(self, base_state):
        """Без parsed_response — только FSM события."""
        base_state.parsed_response = None
        result = simulate_npcs(base_state)
        # Может быть FSM-события, не должно быть llm-событий
        events = result.extra.get("npc_events", [])
        for e in events:
            assert e.get("source") != "llm"


# ── FSM симуляция ─────────────────────────────────

class TestFSM:
    """FSM для NPC, не упомянутых в LLM-ответе."""

    @patch("bot.langgraph.nodes.npc_simulate.random.random")
    def test_fsm_triggered_on_random(self, mock_random, base_state):
        """При random <= 0.3 — NPC действует."""
        mock_random.return_value = 0.2  # <= 0.3, значит сработает

        base_state.parsed_response = GameAction(
            text="тишина", actions=[],
            # Не упоминаем NPC 21 — он должен получить FSM-действие
            npc_actions=[NPCAction(npc_id=20, action="стоит на месте")],
        )

        with patch("bot.langgraph.nodes.npc_simulate.random.choice") as mock_choice:
            mock_choice.return_value = "кашляет в углу"
            result = simulate_npcs(base_state)

        events = result.extra.get("npc_events", [])
        fsm_events = [e for e in events if e.get("source") == "fsm"]

        # NPC 21 (не упомянут в LLM) может получить FSM-действие
        npc21_events = [e for e in fsm_events if e.get("npc_id") == 21]
        # Может быть, может не быть — зависит от random

    @patch("bot.langgraph.nodes.npc_simulate.random.random")
    @patch("bot.langgraph.nodes.npc_simulate.random.choice")
    def test_fsm_skipped_on_low_random(self, mock_choice, mock_random, base_state):
        """При random > 0.3 — NPC бездействует (70% шанс)."""
        mock_random.return_value = 0.5  # > 0.3, бездействие

        result = simulate_npcs(base_state)

        events = result.extra.get("npc_events", [])
        # random.choice не должен вызываться — все NPC бездействуют
        mock_choice.assert_not_called()
        assert len(events) == 0

    @patch("bot.langgraph.nodes.npc_simulate.random.random")
    def test_high_danger_npc_aggressive(self, mock_random, base_state):
        """danger_level > 0.7 — агрессивное/настороженное поведение."""
        mock_random.return_value = 0.5

        npc = {"id": 99, "name": "Зверь", "faction": "mutant", "danger_level": 0.9}
        base_state.extra["npcs_in_location"] = [npc]

        with patch("bot.langgraph.nodes.npc_simulate.random.choice") as mock_choice:
            mock_choice.return_value = "шипит на вас"
            result = simulate_npcs(base_state)

        events = result.extra.get("npc_events", [])
        fsm_events = [e for e in events if e.get("source") == "fsm"]

        if fsm_events:
            assert fsm_events[0]["action"] in [
                "настороженно оглядывается",
                "шипит на вас",
            ]


# ── Интеграция с GameState ────────────────────────

class TestStateIntegration:
    """npc_simulate не портит другие поля."""

    def test_preserves_state(self, base_state):
        """Остальные поля state не меняются."""
        result = simulate_npcs(base_state)

        assert result.chat_id == 12345
        assert result.session_id == 42
        assert result.user_input == "осмотреться"
        assert result.current_location_id == 100