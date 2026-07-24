# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Build Prompt Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды build_prompt.

Не требует БД или LLM — чистое форматирование строк.
"""

from __future__ import annotations

import pytest

from bot.langgraph.nodes.build_prompt import build_prompt
from bot.schemas.game import GameState


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def base_state():
    """Минимальное состояние для сборки промпта."""
    return GameState(
        chat_id=12345,
        user_input="осмотреться",
        session_id=42,
        player_id=10,
        current_location_id=100,
        current_location_name="Коридор секции Б",
        current_cycle=7,
        current_time="14:30",
    )


# ─── Базовая сборка ──────────────────────────────

class TestBasicAssembly:
    """Базовые проверки структуры промпта."""

    def test_prompt_not_empty(self, base_state):
        """Промпт не пустой."""
        result = build_prompt(base_state)
        assert result.prompt is not None
        assert len(result.prompt) > 0

    def test_contains_system_prompt(self, base_state):
        """Промпт содержит системную часть."""
        result = build_prompt(base_state)
        assert "Самосбор" in result.prompt
        assert "мастер игры" in result.prompt.lower()

    def test_contains_user_input(self, base_state):
        """Промпт содержит сообщение пользователя."""
        result = build_prompt(base_state)
        assert "осмотреться" in result.prompt

    def test_contains_json_format(self, base_state):
        """Промпт содержит инструкцию по формату JSON."""
        result = build_prompt(base_state)
        assert "JSON" in result.prompt
        assert "actions" in result.prompt

    def test_contains_game_rules(self, base_state):
        """Промпт содержит правила мира."""
        result = build_prompt(base_state)
        assert "нет окон" in result.prompt.lower()


# ── RAG контекст ─────────────────────────────────

class TestRAGContext:
    """RAG-контекст встраивается в промпт."""

    def test_rag_context_included(self, base_state):
        """Чанки из RAG добавляются в промпт."""
        base_state.rag_context = [
            {"source": "test.txt", "chunk_index": 1,
             "content": "ликвидаторы носят гермокостюмы", "similarity": 0.87,
             "chapter": "Глава 2"},
        ]
        result = build_prompt(base_state)
        assert "ликвидаторы носят гермокостюмы" in result.prompt

    def test_rag_context_empty(self, base_state):
        """Без RAG — промпт не содержит секции контекста."""
        base_state.rag_context = []
        result = build_prompt(base_state)
        assert "Контекст мира" not in result.prompt

    def test_rag_multiple_chunks(self, base_state):
        """Несколько чанков — все в промпте."""
        base_state.rag_context = [
            {"source": "a.txt", "chunk_index": 0, "content": "чанк 1",
             "similarity": 0.9, "chapter": None},
            {"source": "b.txt", "chunk_index": 1, "content": "чанк 2",
             "similarity": 0.8, "chapter": "Глава 1"},
        ]
        result = build_prompt(base_state)
        assert "чанк 1" in result.prompt
        assert "чанк 2" in result.prompt


# ── История диалога ──────────────────────────────

class TestMemory:
    """История диалога встраивается в промпт."""

    def test_memory_included(self, base_state):
        """Сообщения из истории добавляются."""
        base_state.memory = [
            {"role": "user", "content": "войти в комнату", "cycle": 6},
            {"role": "assistant", "content": "вы входите в тёмную комнату", "cycle": 6},
        ]
        result = build_prompt(base_state)
        assert "войти в комнату" in result.prompt
        assert "вы входите в тёмную комнату" in result.prompt

    def test_memory_empty(self, base_state):
        """Без истории — секция истории не появляется."""
        base_state.memory = []
        result = build_prompt(base_state)
        assert "История" not in result.prompt

    def test_long_message_truncated(self, base_state):
        """Длинные сообщения обрезаются."""
        base_state.memory = [
            {"role": "user", "content": "а" * 500, "cycle": 1},
        ]
        result = build_prompt(base_state)
        # Должно быть обрезано до 200 символов
        assert "а" * 200 in result.prompt
        assert "а" * 500 not in result.prompt


# ── Текущая ситуация ─────────────────────────────

class TestCurrentSituation:
    """Информация о локации и NPC в промпте."""

    def test_location_included(self, base_state):
        """Название локации в промпте."""
        result = build_prompt(base_state)
        assert "Коридор секции Б" in result.prompt

    def test_npcs_included(self, base_state):
        """NPC в локации перечислены."""
        base_state.extra["npcs_in_location"] = [
            {"id": 20, "name": "Хромой", "faction": "KPGH", "danger_level": 0.7},
            {"id": 21, "name": "Дохлый", "faction": "Likvidator", "danger_level": 0.3},
        ]
        result = build_prompt(base_state)
        assert "Хромой" in result.prompt
        assert "Дохлый" in result.prompt

    def test_cycle_and_time_included(self, base_state):
        """Цикл и время в промпте."""
        result = build_prompt(base_state)
        assert "7" in result.prompt
        assert "14:30" in result.prompt


# ── Форматирование ───────────────────────────────

class TestFormatting:
    """Проверка структуры и границ."""

    def test_sections_separated(self, base_state):
        """Секции промпта разделены."""
        base_state.memory = [
            {"role": "user", "content": "тест", "cycle": 1},
        ]
        base_state.rag_context = [
            {"source": "test.txt", "chunk_index": 0, "content": "чанк",
             "similarity": 0.9, "chapter": None},
        ]
        result = build_prompt(base_state)
        # Все секции на месте
        assert "## Контекст мира" in result.prompt
        assert "## Текущая ситуация" in result.prompt
        assert "## История" in result.prompt
        assert "## Действие игрока" in result.prompt
        assert "## Ответ" in result.prompt

    def test_prompt_ends_with_format_reminder(self, base_state):
        """Промпт заканчивается напоминанием о JSON."""
        result = build_prompt(base_state)
        assert result.prompt.strip().endswith("Только JSON, без markdown, без пояснений.")


# ── Граничные случаи ─────────────────────────────

class TestEdgeCases:
    """Краевые случаи."""

    def test_very_long_user_input(self, base_state):
        """Очень длинный user_input не ломает промпт."""
        base_state.user_input = "а" * 5000
        result = build_prompt(base_state)
        assert result.prompt is not None
        assert len(result.prompt) > 0

    def test_special_characters(self, base_state):
        """Спецсимволы в user_input."""
        base_state.user_input = "проверить <script>alert('xss')</script> &amp;"
        result = build_prompt(base_state)
        assert result.prompt is not None

    def test_all_fields_empty(self):
        """Максимально пустое состояние — не падаем."""
        state = GameState(chat_id=1, user_input="тест")
        result = build_prompt(state)
        assert result.prompt is not None
        assert "Самосбор" in result.prompt  # системный промпт есть всегда

    def test_rag_without_chapter(self, base_state):
        """Чанк без главы — не падаем."""
        base_state.rag_context = [
            {"source": "test.txt", "chunk_index": 0,
             "content": "текст", "similarity": 0.5, "chapter": None},
        ]
        result = build_prompt(base_state)
        assert "текст" in result.prompt