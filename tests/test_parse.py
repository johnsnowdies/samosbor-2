# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Parse Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды parse.

Проверяют извлечение JSON из разных форматов ответа LLM
и валидацию через Pydantic.
"""

from __future__ import annotations

import pytest

from bot.langgraph.nodes.parse import parse_response
from bot.schemas.game import GameState


# ── Fixture ───────────────────────────────────────

@pytest.fixture
def base_state():
    """Состояние с ответом LLM."""
    return GameState(chat_id=12345, user_input="осмотреться")


def make_state_with_response(llm_response: str) -> GameState:
    """Создаёт state с заданным ответом LLM."""
    return GameState(chat_id=12345, user_input="тест", llm_response=llm_response)


# ── Извлечение JSON ───────────────────────────────

class TestJSONExtraction:
    """Разные форматы ответа LLM."""

    def test_raw_json(self):
        """Чистый JSON без обёртки."""
        state = make_state_with_response(
            '{"text": "вы в коридоре", "actions": ["идти"], "game_over": false}'
        )
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response is not None
        assert result.parsed_response.text == "вы в коридоре"
        assert result.parsed_response.actions == ["идти"]

    def test_json_in_code_block(self):
        """JSON внутри ```json ... ```."""
        state = make_state_with_response(
            '```json\n{"text": "комната", "actions": ["осмотреться"], "game_over": false}\n```'
        )
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "комната"

    def test_json_in_code_block_no_lang(self):
        """JSON внутри ``` ... ``` без указания языка."""
        state = make_state_with_response(
            '```\n{"text": "test", "actions": [], "game_over": false}\n```'
        )
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "test"

    def test_json_with_trailing_text(self):
        """Текст после JSON игнорируется."""
        state = make_state_with_response(
            '{"text": "ok", "actions": ["a"], "game_over": false}\n\n(это пояснение)'
        )
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "ok"

    def test_json_with_leading_text(self):
        """Текст до JSON игнорируется."""
        state = make_state_with_response(
            'Вот ответ:\n\n{"text": "ok", "actions": ["a"], "game_over": false}'
        )
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "ok"

    def test_full_code_block_with_extra(self):
        """```json блок с текстом до и после."""
        state = make_state_with_response(
            'Вот JSON:\n```json\n{"text": "да", "actions": ["нет"], "game_over": false}\n```\nКонец.'
        )
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "да"

    def test_empty_code_block(self):
        """Пустой ```json блок — ошибка."""
        state = make_state_with_response("```json\n\n```")
        result = parse_response(state)
        assert result.error is not None

    def test_malformed_json(self):
        """Кривой JSON — ошибка."""
        state = make_state_with_response('{"text": missing quotes}')
        result = parse_response(state)
        assert result.error is not None
        assert "JSON" in result.error


# ── Валидация Pydantic ────────────────────────────

class TestPydanticValidation:
    """Проверка полей через GameAction."""

    def test_all_fields_present(self):
        """Все поля GameAction заполнены."""
        json_str = '''{
            "text": "описание",
            "actions": ["а", "б", "в"],
            "items": ["ключ"],
            "quests": ["найти воду"],
            "game_over": false,
            "location": "кухня",
            "location_id": 5,
            "image_prompt": "dark kitchen"
        }'''
        state = make_state_with_response(json_str)
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "описание"
        assert len(result.parsed_response.actions) == 3
        assert "ключ" in result.parsed_response.items
        assert "найти воду" in result.parsed_response.quests
        assert result.parsed_response.location == "кухня"
        assert result.parsed_response.location_id == 5
        assert result.parsed_response.image_prompt == "dark kitchen"

    def test_minimal_fields(self):
        """Только обязательные поля (text, actions)."""
        json_str = '{"text": "тишина", "actions": []}'
        state = make_state_with_response(json_str)
        result = parse_response(state)
        assert result.error is None
        assert result.parsed_response.text == "тишина"
        assert result.parsed_response.game_over is False  # default

    def test_invalid_field_type(self):
        """actions не список — ошибка валидации."""
        json_str = '{"text": "оп", "actions": "не список", "game_over": false}'
        state = make_state_with_response(json_str)
        result = parse_response(state)
        assert result.error is not None
        assert "actions" in result.error.lower() or "формат" in result.error.lower()


# ── game_over ─────────────────────────────────────

class TestGameOverField:
    """Нормализация game_over."""

    def test_bool_false(self):
        """game_over: false — корректно."""
        state = make_state_with_response(
            '{"text": "x", "actions": [], "game_over": false}'
        )
        result = parse_response(state)
        assert result.parsed_response.game_over is False

    def test_bool_true(self):
        """game_over: true — корректно."""
        state = make_state_with_response(
            '{"text": "x", "actions": [], "game_over": true}'
        )
        result = parse_response(state)
        assert result.parsed_response.game_over is True

    def test_string_false(self):
        """game_over: 'false' (строка) — нормализуется в False."""
        state = make_state_with_response(
            '{"text": "x", "actions": [], "game_over": "false"}'
        )
        result = parse_response(state)
        assert result.parsed_response.game_over is False

    def test_string_true(self):
        """game_over: 'true' (строка) — нормализуется в True."""
        state = make_state_with_response(
            '{"text": "x", "actions": [], "game_over": "true"}'
        )
        result = parse_response(state)
        assert result.parsed_response.game_over is True

    def test_default_false(self):
        """game_over отсутствует — default False."""
        state = make_state_with_response('{"text": "x", "actions": []}')
        result = parse_response(state)
        assert result.parsed_response.game_over is False


# ── Пустой ответ ─────────────────────────────────

class TestEmptyResponse:
    """Нет ответа от LLM."""

    def test_no_response(self, base_state):
        """llm_response = None — ошибка."""
        result = parse_response(base_state)
        assert result.error is not None
        assert "нет ответа" in result.error.lower()

    def test_empty_string(self):
        """llm_response = '' — ошибка."""
        state = make_state_with_response("")
        result = parse_response(state)
        assert result.error is not None


# ── Состояние без изменений ──────────────────────

class TestStateConsistency:
    """parse не портит другие поля."""

    def test_preserves_state(self):
        """Остальные поля state не меняются."""
        state = GameState(
            chat_id=12345,
            user_input="тест",
            session_id=42,
            player_id=10,
            current_cycle=7,
            llm_response='{"text": "x", "actions": [], "game_over": false}',
        )
        result = parse_response(state)
        assert result.chat_id == 12345
        assert result.session_id == 42
        assert result.player_id == 10
        assert result.current_cycle == 7