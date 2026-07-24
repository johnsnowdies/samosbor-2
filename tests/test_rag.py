# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — RAG Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды rag.

Все внешние вызовы (Ollama, pgvector) замоканы.
"""

from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from bot.langgraph.nodes.rag import retrieve_rag
from bot.schemas.game import GameState


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def mock_db():
    """Замоканная SQLAlchemy сессия."""
    return MagicMock()


@pytest.fixture
def base_state():
    """Базовое состояние с запросом."""
    return GameState(chat_id=12345, user_input="кто такие ликвидаторы")


def make_mock_row(source: str, chunk_index: int, content: str,
                  similarity: float, chapter: str | None = None):
    """Создаёт замоканную строку результата из БД."""
    row = MagicMock()
    row.source = source
    row.chunk_index = chunk_index
    row.content = content
    row.similarity = similarity
    row.extra_meta = {"chapter": chapter} if chapter else {}
    return row


# ── Успешный поиск ─────────────────────────────────

class TestSuccessfulRAG:
    """Поиск возвращает чанки."""

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_returns_chunks(self, mock_embed, mock_db, base_state):
        """Обычный запрос — возвращает топ-K чанков."""
        mock_embed.return_value = [0.1] * 1024

        mock_rows = [
            make_mock_row("Гигахрущ.txt", 12, "Ликвидаторы носят герметичные костюмы", 0.87, "Глава 2"),
            make_mock_row("Этажи.txt", 45, "Отряд ликвидаторов вошёл в сектор Б", 0.82, "Глава 5"),
            make_mock_row("Бетонное Сердце.txt", 7, "Ликвидатор взвел курок", 0.76, None),
        ]
        mock_db.execute.return_value.fetchall.return_value = mock_rows

        result = retrieve_rag(base_state, mock_db)

        assert result.error is None
        assert len(result.rag_context) == 3
        assert result.rag_context[0]["source"] == "Гигахрущ.txt"
        assert result.rag_context[0]["similarity"] == 0.87
        assert result.rag_context[0]["chapter"] == "Глава 2"
        assert result.rag_context[2]["chapter"] is None

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_content_truncated(self, mock_embed, mock_db, base_state):
        """Длинный контент обрезается до MAX_CHUNK_LENGTH."""
        from bot.langgraph.nodes.rag import MAX_CHUNK_LENGTH

        mock_embed.return_value = [0.1] * 1024
        long_text = "а" * (MAX_CHUNK_LENGTH + 100)
        mock_rows = [
            make_mock_row("test.txt", 0, long_text, 0.9),
        ]
        mock_db.execute.return_value.fetchall.return_value = mock_rows

        result = retrieve_rag(base_state, mock_db)

        assert len(result.rag_context[0]["content"]) == MAX_CHUNK_LENGTH


# ── Пустой запрос ─────────────────────────────────

class TestEmptyQuery:
    """Пустой запрос — не идём в эмбедер и БД."""

    def test_empty_string(self, mock_db):
        """Пустая строка — пустой rag_context."""
        state = GameState(chat_id=12345, user_input="")
        result = retrieve_rag(state, mock_db)
        assert result.rag_context == []
        mock_db.execute.assert_not_called()

    def test_whitespace_only(self, mock_db):
        """Пробелы — пустой rag_context."""
        state = GameState(chat_id=12345, user_input="   \n  ")
        result = retrieve_rag(state, mock_db)
        assert result.rag_context == []
        mock_db.execute.assert_not_called()


# ── Нет результатов ────────────────────────────────

class TestNoResults:
    """Поиск ничего не нашёл."""

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_empty_results(self, mock_embed, mock_db, base_state):
        """БД пуста или ничего не найдено — пустой список."""
        mock_embed.return_value = [0.1] * 1024
        mock_db.execute.return_value.fetchall.return_value = []

        result = retrieve_rag(base_state, mock_db)

        assert result.rag_context == []


# ── Ошибка эмбединга ──────────────────────────────

class TestEmbeddingError:
    """Ошибка при вызове Ollama — не падаем, возвращаем пустой контекст."""

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_embedder_fails_gracefully(self, mock_embed, mock_db, base_state):
        """Ошибка эмбединга — пустой rag_context, error не ставится."""
        mock_embed.side_effect = Exception("Ollama timeout")

        result = retrieve_rag(base_state, mock_db)

        assert result.error is None  # RAG не критичен
        assert result.rag_context == []


# ── Ошибка БД ─────────────────────────────────────

class TestDBError:
    """Ошибка при запросе к pgvector — не падаем."""

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_db_fails_gracefully(self, mock_embed, mock_db, base_state):
        """Ошибка БД — пустой rag_context."""
        mock_embed.return_value = [0.1] * 1024
        mock_db.execute.side_effect = Exception("connection refused")

        result = retrieve_rag(base_state, mock_db)

        assert result.error is None
        assert result.rag_context == []


# ── Формат чанков ─────────────────────────────────

class TestChunkFormat:
    """Проверка структуры возвращаемых чанков."""

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_chunk_structure(self, mock_embed, mock_db, base_state):
        """Каждый чанк содержит все обязательные поля."""
        mock_embed.return_value = [0.1] * 1024
        mock_rows = [
            make_mock_row("test.txt", 5, "какой-то текст", 0.75, "Глава 1"),
        ]
        mock_db.execute.return_value.fetchall.return_value = mock_rows

        result = retrieve_rag(base_state, mock_db)

        chunk = result.rag_context[0]
        assert "source" in chunk
        assert "chunk_index" in chunk
        assert "content" in chunk
        assert "similarity" in chunk
        assert "chapter" in chunk
        assert chunk["source"] == "test.txt"
        assert chunk["chunk_index"] == 5
        assert chunk["similarity"] == 0.75
        assert chunk["chapter"] == "Глава 1"

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_extra_meta_without_chapter(self, mock_embed, mock_db, base_state):
        """extra_meta без chapter — chapter = None."""
        mock_embed.return_value = [0.1] * 1024

        row = MagicMock()
        row.source = "test.txt"
        row.chunk_index = 0
        row.content = "текст"
        row.similarity = 0.5
        row.extra_meta = {"file_hash": "abc123"}  # нет chapter
        mock_db.execute.return_value.fetchall.return_value = [row]

        result = retrieve_rag(base_state, mock_db)

        assert result.rag_context[0]["chapter"] is None


# ── Интеграция с GameState ────────────────────────

class TestStateIntegration:
    """RAG не портит другие поля GameState."""

    @patch("bot.langgraph.nodes.rag.embed_text")
    def test_preserves_existing_state(self, mock_embed, mock_db):
        """Другие поля state не меняются."""
        mock_embed.return_value = [0.1] * 1024
        mock_db.execute.return_value.fetchall.return_value = []

        state = GameState(
            chat_id=12345,
            user_input="проверить",
            session_id=42,
            player_id=10,
            current_location_id=100,
            current_cycle=7,
        )

        result = retrieve_rag(state, mock_db)

        assert result.chat_id == 12345
        assert result.session_id == 42
        assert result.player_id == 10
        assert result.current_location_id == 100
        assert result.current_cycle == 7