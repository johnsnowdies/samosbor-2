# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Update State Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды update_state.

Все запросы к БД замоканы.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from bot.langgraph.nodes.update_state import update_state
from bot.schemas.game import GameAction, GameState


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def base_state():
    """Состояние после успешного парсинга."""
    return GameState(
        chat_id=12345,
        user_input="открыть дверь",
        session_id=42,
        player_id=10,
        current_cycle=7,
        current_time="14:30",
        parsed_response=GameAction(
            text="Вы открыли дверь и вошли в тёмную комнату.",
            actions=["осмотреться", "вернуться"],
        ),
    )


def make_mock_session(**kwargs):
    session = MagicMock()
    session.id = kwargs.get("id", 42)
    session.game_over = kwargs.get("game_over", False)
    session.current_cycle = kwargs.get("current_cycle", 7)
    session.current_time = kwargs.get("current_time", "14:30")
    return session


def make_mock_person(**kwargs):
    person = MagicMock()
    person.id = kwargs.get("id", 10)
    person.current_location_id = kwargs.get("current_location_id", 100)
    return person


def make_mock_location(**kwargs):
    loc = MagicMock()
    loc.id = kwargs.get("id", 200)
    loc.name = kwargs.get("name", "Тёмная комната")
    loc.session_id = kwargs.get("session_id", 42)
    return loc


# ── Успешное сохранение ─────────────────────────

class TestSuccessfulSave:
    """Обычный ход — сохраняем всё."""

    def test_saves_conversation_history(self, mock_db, base_state):
        """Сообщение пользователя и ответ сохраняются в историю."""
        mock_session = make_mock_session()
        mock_person = make_mock_person()
        mock_db.get.side_effect = lambda model, pk: {
            (MagicMock.__name__ if hasattr(model, '__name__') else str(model), 42): mock_session,
            (MagicMock.__name__ if hasattr(model, '__name__') else str(model), 10): mock_person,
        }.get((model.__name__ if hasattr(model, '__name__') else '', pk))

        # db.get возвращает правильные объекты
        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        result = update_state(base_state, mock_db)

        assert result.error is None
        # Должны быть добавлены 2 сообщения: user + assistant
        assert mock_db.add.call_count >= 2

    def test_increments_cycle(self, mock_db, base_state):
        """Цикл увеличивается на 1."""
        mock_session = make_mock_session()
        mock_person = make_mock_person()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        result = update_state(base_state, mock_db)

        assert result.current_cycle == 8  # 7 + 1
        assert mock_session.current_cycle == 8

    def test_updates_time(self, mock_db, base_state):
        """Время увеличивается на 1 час."""
        mock_session = make_mock_session()
        mock_person = make_mock_person()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        result = update_state(base_state, mock_db)

        assert result.current_time == "15:00"

    def test_commits(self, mock_db, base_state):
        """Вызывается db.commit()."""
        mock_session = make_mock_session()
        mock_person = make_mock_person()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        update_state(base_state, mock_db)

        assert mock_db.commit.called


# ── game_over ──────────────────────────────────────

class TestGameOver:
    """Завершение игры."""

    def test_game_over_sets_flag(self, mock_db, base_state):
        """game_over=True — сессия помечается завершённой."""
        base_state.parsed_response = GameAction(
            text="Вы погибли.", actions=[], game_over=True,
        )
        mock_session = make_mock_session()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__') and model.__name__ == "GameSession" and pk == 42:
                return mock_session
            return None
        mock_db.get.side_effect = get_side_effect

        update_state(base_state, mock_db)

        assert mock_session.game_over is True


# ── Смена локации ─────────────────────────────────

class TestLocationChange:
    """Перемещение в другую локацию."""

    def test_updates_location(self, mock_db, base_state):
        """При смене локации — Person.current_location_id обновляется."""
        base_state.parsed_response = GameAction(
            text="Вы вошли.", actions=[], location="Тёмная комната",
        )
        mock_session = make_mock_session()
        mock_person = make_mock_person()
        mock_location = make_mock_location()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        # query().filter().first() — для поиска локации по имени
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_location
        mock_db.query.return_value = mock_query

        result = update_state(base_state, mock_db)

        assert mock_person.current_location_id == 200

    def test_no_location_change(self, mock_db, base_state):
        """Без location в ответе — локация не меняется."""
        mock_session = make_mock_session()
        mock_person = make_mock_person()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        result = update_state(base_state, mock_db)

        assert mock_person.current_location_id == 100  # не изменился


# ── Нет session_id ────────────────────────────────

class TestNoSession:
    """Нет сессии — не сохраняем."""

    def test_no_session_id(self, mock_db, base_state):
        """session_id = None — ошибка."""
        base_state.session_id = None
        result = update_state(base_state, mock_db)
        assert result.error is not None
        assert "session_id" in result.error.lower()


# ── Нет parsed_response ───────────────────────────

class TestNoAction:
    """Нет распарсенного ответа — пропускаем."""

    def test_no_parsed_response(self, mock_db, base_state):
        """parsed_response = None — ничего не сохраняем."""
        base_state.parsed_response = None
        result = update_state(base_state, mock_db)
        assert result.error is None  # не ошибка, просто пропуск
        assert not mock_db.commit.called


# ── Время оборачивается ───────────────────────────

class TestTimeWrap:
    """Переход через полночь."""

    def test_time_wraps_after_23(self, mock_db, base_state):
        """23:00 + 1 = 00:00"""
        base_state.current_time = "23:00"
        mock_session = make_mock_session(current_time="23:00")
        mock_person = make_mock_person()

        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "GameSession" and pk == 42:
                    return mock_session
                if model.__name__ == "Person" and pk == 10:
                    return mock_person
            return None
        mock_db.get.side_effect = get_side_effect

        result = update_state(base_state, mock_db)

        assert result.current_time == "00:00"