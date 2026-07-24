# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Start Game Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды start_game.

Все запросы к БД замоканы.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from bot.langgraph.nodes.start_game import start_game
from bot.schemas.game import GameState


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def mock_db():
    """Замоканная SQLAlchemy сессия."""
    return MagicMock()


@pytest.fixture
def base_state():
    """Состояние с командой /start."""
    return GameState(chat_id=12345, user_input="/start")


def make_mock_user(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.telegram_chat_id = kwargs.get("telegram_chat_id", 12345)
    user.is_allowed = kwargs.get("is_allowed", True)
    user.balance = kwargs.get("balance", 10)
    user.trial_messages_left = kwargs.get("trial_messages_left", 5)
    return user


def make_mock_session(**kwargs):
    session = MagicMock()
    session.id = kwargs.get("id", 99)
    session.user_id = kwargs.get("user_id", 1)
    session.game_over = kwargs.get("game_over", False)
    session.current_cycle = kwargs.get("current_cycle", 1)
    session.current_time = kwargs.get("current_time", "08:00")
    session.created_at = datetime.now(timezone.utc)
    return session


# ── Новый пользователь ─────────────────────────────

class TestNewUser:
    """Пользователя нет в БД — создаём."""

    def test_creates_user_and_session(self, mock_db, base_state):
        """Новый пользователь — создаётся User и GameSession."""
        # Пользователь не найден
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            None,  # пользователь не найден
            None,  # старая сессия не найдена
        ]

        # GameSession создаётся с id=42 после refresh
        mock_new_session = MagicMock()
        mock_new_session.id = 42
        mock_new_session.user_id = 1

        def refresh_side_effect(obj):
            if hasattr(obj, 'user_id'):
                # Симулируем что объект получил id из БД
                obj.id = 42

        mock_db.refresh.side_effect = refresh_side_effect

        result = start_game(base_state, mock_db)

        # Проверяем что User был создан
        assert mock_db.add.called
        assert mock_db.commit.called

        assert result.error is None
        assert result.session_id == 42
        assert result.current_cycle == 1
        assert result.current_time == "08:00"
        assert result.is_allowed is True

    def test_new_user_has_trial(self, mock_db, base_state):
        """Новый пользователь получает 5 триальных сообщений."""
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            None, None,
        ]

        # Перехватываем создание User
        added_users = []

        def add_side_effect(obj):
            if hasattr(obj, 'trial_messages_left'):
                added_users.append(obj)

        mock_db.add.side_effect = add_side_effect

        start_game(base_state, mock_db)

        assert len(added_users) >= 1
        user = added_users[0]
        assert user.trial_messages_left == 5
        assert user.is_allowed is True
        assert user.telegram_chat_id == 12345


# ── Существующий пользователь ─────────────────────

class TestExistingUser:
    """Пользователь уже есть — просто создаём новую сессию."""

    def test_uses_existing_user(self, mock_db, base_state):
        """Пользователь найден — не создаём нового."""
        mock_user = make_mock_user()

        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,  # пользователь существует
            None,       # старая сессия не найдена
        ]

        add_called = []

        def add_side_effect(obj):
            if hasattr(obj, 'user_id'):
                add_called.append(obj)

        mock_db.add.side_effect = add_side_effect

        result = start_game(base_state, mock_db)

        assert result.error is None
        # Session была добавлена (одна)
        assert len(add_called) >= 1

    def test_closes_old_session(self, mock_db, base_state):
        """Если есть активная сессия — завершаем её."""
        mock_user = make_mock_user()
        mock_old_session = make_mock_session(id=50)

        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,
            mock_old_session,  # старая активная сессия
        ]

        result = start_game(base_state, mock_db)

        assert mock_old_session.game_over is True
        assert result.error is None


# ── Забаненный ────────────────────────────────────

class TestBannedUser:
    """Забаненный пользователь — ошибка."""

    def test_banned_user_cannot_start(self, mock_db, base_state):
        """is_allowed=False — ошибка."""
        mock_user = make_mock_user(is_allowed=False)

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user

        result = start_game(base_state, mock_db)

        assert result.error is not None
        assert "доступ запрещён" in result.error.lower()


# ── Промпт ─────────────────────────────────────────

class TestStartPrompt:
    """Промпт для старта игры."""

    def test_start_prompt_not_set(self, mock_db, base_state):
        """После start_game prompt не установлен — его соберёт build_prompt."""
        mock_user = make_mock_user()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,
            None,
        ]

        result = start_game(base_state, mock_db)

        assert result.prompt is None, "prompt теперь собирает build_prompt"
        assert result.is_new_game is True, "is_new_game должен быть True после /start"


# ── Состояние ─────────────────────────────────────

class TestStateAfterStart:
    """Проверка полей state после старта."""

    def test_game_over_false(self, mock_db, base_state):
        """game_over должен быть False."""
        mock_user = make_mock_user()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,
            None,
        ]

        result = start_game(base_state, mock_db)

        assert result.game_over is False

    def test_cycle_reset(self, mock_db, base_state):
        """current_cycle сбрасывается в 1."""
        mock_user = make_mock_user()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,
            None,
        ]

        result = start_game(base_state, mock_db)

        assert result.current_cycle == 1

    def test_player_id_none(self, mock_db, base_state):
        """player_id должен быть None (ещё не создан)."""
        mock_user = make_mock_user()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,
            None,
        ]

        result = start_game(base_state, mock_db)

        assert result.player_id is None