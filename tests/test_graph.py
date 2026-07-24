# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Graph Assembly Tests
# ─────────────────────────────────────────────────

"""
Тесты для сборки графа.

Проверяют:
  - Структуру графа (ноды, рёбра)
  - Маршрутизацию (/start vs обычное сообщение)
  - Обработку ошибок (has_error)
  - Компиляцию
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bot.langgraph.graph import (
    build_game_graph,
    has_error,
    is_start_command,
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
    """has_error проверяет state.error."""

    def test_no_error(self):
        """Без ошибки — continue."""
        state = GameState(chat_id=1, user_input="тест")
        assert has_error(state) == "continue"

    def test_with_error(self):
        """С ошибкой — end."""
        state = GameState(chat_id=1, user_input="тест", error="ошибка")
        assert has_error(state) == "end"


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
            "guardrails",
            "memory",
            "rag",
            "build_prompt",
            "llm_call",
            "parse",
            "update_state",
            "npc_simulate",
        ]
        for node in expected_nodes:
            assert node in graph.nodes, f"Нода '{node}' отсутствует в графе"


# ── Интеграция (лёгкая) ────────────────────────

class TestLightIntegration:
    """Лёгкая проверка что граф не падает с моками."""

    @patch("bot.models.base.SessionLocal")
    @patch("bot.langgraph.nodes.llm_call._get_client")
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

        # Мок DB — все запросы возвращают None
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
    def test_graph_runs_start_command(self, mock_db, capsys):
        """/start проходит через start_game."""
        mock_db_session = MagicMock()
        mock_db.return_value = mock_db_session
        mock_db_session.execute.return_value.scalar_one_or_none.side_effect = [
            None, None,  # user not found, old session not found
        ]

        # После start_game — идёт llm_call. Мокаем LLM.
        with patch("bot.langgraph.nodes.llm_call._get_client") as mock_llm:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = (
                '{"text": "начало", "actions": ["идти"], "game_over": false}'
            )
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_llm.return_value = mock_client

            graph = build_game_graph()
            state = GameState(chat_id=12345, user_input="/start")
            result = graph.invoke(state)

        assert result is not None