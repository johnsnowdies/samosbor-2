# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — LLM Call Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды llm_call.

Все вызовы OpenRouter замоканы — реальных запросов нет.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bot.langgraph.nodes.llm_call import call_llm
from bot.schemas.game import GameState


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def base_state():
    """Состояние с готовым промптом."""
    return GameState(
        chat_id=12345,
        user_input="осмотреться",
        prompt="Ты — мастер игры. Игрок осматривается.",
    )


# ── Успешный вызов ────────────────────────────────

class TestSuccessfulCall:
    """LLM возвращает ответ."""

    @patch("openai.OpenAI")
    def test_returns_response(self, mock_get_client, base_state):
        """Ответ LLM сохраняется в state.llm_response."""
        # Настройка мока
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "```json\n{\"text\": \"вы в коридоре\"}\n```"
        mock_response.choices = [mock_choice]

        # Мокаем usage для лога
        mock_usage = MagicMock()
        mock_usage.total_tokens = 150
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_response.usage = mock_usage

        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = call_llm(base_state)

        assert result.error is None
        assert result.llm_response is not None
        assert "вы в коридоре" in result.llm_response

    @patch("openai.OpenAI")
    def test_llm_called_with_correct_args(self, mock_get_client, base_state):
        """Проверка, что LLM вызван с правильными параметрами."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ответ"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from bot.langgraph.nodes.llm_call import LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

        call_llm(base_state)

        mock_client.chat.completions.create.assert_called_once_with(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": base_state.prompt}],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )

    @patch("openai.OpenAI")
    def test_response_stripped(self, mock_get_client, base_state):
        """Пробелы по краям ответа обрезаются."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "  {\"text\": \"тест\"}  \n"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = call_llm(base_state)

        assert result.llm_response == '{"text": "тест"}'


# ── Пустой промпт ─────────────────────────────────

class TestEmptyPrompt:
    """Пустой промпт — не вызываем LLM."""

    @patch("openai.OpenAI")
    def test_empty_prompt_skips_llm(self, mock_get_client, base_state):
        """Промпт пустой — ошибка, LLM не вызывается."""
        base_state.prompt = None
        result = call_llm(base_state)

        assert result.error is not None
        assert "пустой" in result.error.lower()
        mock_get_client.assert_not_called()


# ── Ошибка LLM ────────────────────────────────────

class TestLLMError:
    """Ошибка при вызове LLM."""

    @patch("openai.OpenAI")
    def test_api_error(self, mock_get_client, base_state):
        """Ошибка API — error в state, llm_response пустой."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API timeout")
        mock_get_client.return_value = mock_client

        result = call_llm(base_state)

        assert result.error is not None
        assert "API timeout" in result.error
        assert result.llm_response is None

    @patch("openai.OpenAI")
    def test_empty_response(self, mock_get_client, base_state):
        """LLM вернул пустой ответ — ошибка."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = call_llm(base_state)

        assert result.error is not None


# ── Конфигурация ──────────────────────────────────

class TestConfiguration:
    """Проверка env-конфигурации LLM."""

    @patch("bot.langgraph.nodes.llm_call.OPENROUTER_API_KEY", "")
    @patch("openai.OpenAI")
    def test_no_api_key(self, mock_get_client, base_state):
        """Без API ключа — ошибка при создании клиента."""
        mock_get_client.side_effect = ValueError(
            "OPENROUTER_API_KEY не задан"
        )

        result = call_llm(base_state)

        assert result.error is not None
        assert "OPENROUTER_API_KEY" in result.error or "API" in result.error


# ── Интеграция с GameState ────────────────────────

class TestStateIntegration:
    """llm_call не портит другие поля."""

    @patch("openai.OpenAI")
    def test_preserves_state(self, mock_get_client, base_state):
        """Другие поля не меняются."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ответ"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        base_state.session_id = 42
        base_state.player_id = 10
        base_state.current_cycle = 7

        result = call_llm(base_state)

        assert result.chat_id == 12345
        assert result.session_id == 42
        assert result.player_id == 10
        assert result.current_cycle == 7
        assert result.user_input == "осмотреться"