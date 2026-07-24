# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Graph Assembly Tests
# ─────────────────────────────────────────────────

"""
Тесты для сборки графа.

Проверяют:
  - Структуру графа (ноды, рёбра)
  - Маршрутизацию (/start vs обычное сообщение)
  - Обработку ошибок (роутинг)
  - Компиляцию
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langgraph.graph import END

from bot.langgraph.graph import (
    build_game_graph,
    is_start_command,
    route_after_generate_world,
    route_after_guardrails,
)
from bot.schemas.game import GameState


# ── Маршрутизация ───────────────────────────────

class TestRouting:
    """is_start_command определяет путь сообщения."""

    def test_start_command(self):
        """/start → start_game."""
        state = GameState(chat_id=1, user_input="/start")
        assert is_start_command(state) == "start_game"

    def test_start_with_whitespace(self):
        """/start с пробелами → start_game."""
        state = GameState(chat_id=1, user_input="  /start  ")
        assert is_start_command(state) == "start_game"

    def test_regular_message(self):
        """Обычное сообщение → guardrails."""
        state = GameState(chat_id=1, user_input="осмотреться")
        assert is_start_command(state) == "guardrails"

    def test_start_in_middle(self):
        """/start не в начале — не срабатывает."""
        state = GameState(chat_id=1, user_input="скажи /start")
        assert is_start_command(state) == "guardrails"


# ── Обработка ошибок ────────────────────────────

class TestErrorHandling:
    """Роутеры проверяют state.error."""

    def test_no_error_continues(self):
        """Без ошибки — идёт к следующей ноде."""
        state = GameState(chat_id=1, user_input="тест")
        assert route_after_guardrails(state) == "validate_action"

    def test_error_ends(self):
        """С ошибкой — END."""
        state = GameState(chat_id=1, user_input="тест", error="ошибка")
        assert route_after_guardrails(state) is END

    def test_generate_world_error(self):
        """generate_world с ошибкой → END."""
        state = GameState(chat_id=1, user_input="/start", error="ошибка")
        assert route_after_generate_world(state) is END


# ── Структура графа ─────────────────────────────

class TestGraphStructure:
    """Проверка нод и рёбер."""

    def test_graph_compiles(self):
        """Граф компилируется без ошибок."""
        graph = build_game_graph()
        assert graph is not None

    def test_has_all_nodes(self):
        """Все ноды присутствуют."""
        graph = build_game_graph()
        expected_nodes = [
            "start_game",
            "generate_world",
            "guardrails",
            "validate_action",
            "memory",
            "rag",
            "build_prompt",
            "llm_call",
            "parse",
            "update_state",
            "generate_locations",
            "fact_check",
            "npc_simulate",
        ]
        for node in expected_nodes:
            assert node in graph.nodes, f"Нода '{node}' отсутствует в графе"


# ── Интеграция (лёгкая) ────────────────────────

class TestLightIntegration:
    """Лёгкая проверка что граф не падает с моками."""

    @patch("bot.models.base.SessionLocal")
    @patch("openai.OpenAI")
    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_graph_runs_regular_message(self, mock_embed, mock_llm, mock_db, capsys):
        """Обычное сообщение проходит весь граф."""
        mock_embed.return_value = [0.1] * 1024

        # Мок LLM
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"text": "вы в коридоре", "actions": ["идти"], "game_over": false}'
        )
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_llm.return_value = mock_client

        # Мок DB
        mock_db_session = MagicMock()
        mock_db.return_value = mock_db_session
        mock_db_session.execute.return_value.scalar_one_or_none.side_effect = [
            None, None, None,
        ]
        mock_db_session.get.return_value = None
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        graph = build_game_graph()

        state = GameState(chat_id=12345, user_input="осмотреться")
        result = graph.invoke(state)

        assert result is not None
        # Должен быть error, т.к. пользователь не найден в memory
        assert result.get("error") is not None

    @patch("bot.models.base.SessionLocal")
    @patch("openai.OpenAI")
    def test_graph_runs_start_command(self, mock_llm, mock_db, capsys):
        """/start проходит через start_game и generate_world (с моками)."""
        mock_db_session = MagicMock()
        mock_db.return_value = mock_db_session
        mock_db_session.execute.return_value.scalar_one_or_none.side_effect = [
            None, None,  # user not found, old session not found
        ]
        # Мок для всех get/save операций
        mock_db_session.get.return_value = None
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        mock_db_session.add.return_value = None
        mock_db_session.flush.return_value = None
        mock_db_session.commit.return_value = None

        # Мок для generate_world (возвращает JSON + не падает)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"player_name": "Тест", "start_location": "Комната", '
            '"locations": [{"name": "Комната", "description": "", "floor": "1"}], '
            '"floors": [{"name": "1", "danger_level": 0.3}], '
            '"connections": [], "items": [], "npcs": [], "npc_relations": [], '
            '"quests": []}'
        )
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_llm.return_value = mock_client

        graph = build_game_graph()
        state = GameState(chat_id=12345, user_input="/start")
        result = graph.invoke(state)

        assert result is not None