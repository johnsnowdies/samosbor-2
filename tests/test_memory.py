# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Memory Node Tests
# ─────────────────────────────────────────────────

"""
Тесты для ноды memory.

Все запросы к БД замоканы — тесты не требуют живой базы.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from bot.langgraph.nodes.memory import load_memory
from bot.schemas.game import GameState


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def mock_db():
    """Создаёт замоканную SQLAlchemy сессию."""
    return MagicMock()


@pytest.fixture
def base_state():
    """Базовое состояние с chat_id."""
    return GameState(chat_id=12345, user_input="осмотреться")


def make_mock_user(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.telegram_chat_id = kwargs.get("telegram_chat_id", 12345)
    user.is_allowed = kwargs.get("is_allowed", True)
    user.balance = kwargs.get("balance", 10)
    user.trial_messages_left = 0
    return user


def make_mock_session(**kwargs):
    session = MagicMock()
    session.id = kwargs.get("id", 42)
    session.user_id = kwargs.get("user_id", 1)
    session.game_over = kwargs.get("game_over", False)
    session.current_cycle = kwargs.get("current_cycle", 7)
    session.current_time = kwargs.get("current_time", "14:30")
    session.created_at = datetime.now(timezone.utc)
    return session


def make_mock_player(**kwargs):
    player = MagicMock()
    player.person_id = kwargs.get("person_id", 10)
    player.session_id = kwargs.get("session_id", 42)
    return player


def make_mock_person(**kwargs):
    person = MagicMock()
    person.id = kwargs.get("id", 10)
    person.name = kwargs.get("name", "Выживший")
    person.current_location_id = kwargs.get("current_location_id", 100)
    person.session_id = kwargs.get("session_id", 42)
    return person


def make_mock_location(**kwargs):
    loc = MagicMock()
    loc.id = kwargs.get("id", 100)
    loc.name = kwargs.get("name", "Коридор секции Б")
    loc.description = kwargs.get("description", "Тёмный коридор с мерцающими лампами")
    return loc


def make_mock_npc(**kwargs):
    npc = MagicMock()
    npc.person_id = kwargs.get("person_id", 20)
    npc.faction = kwargs.get("faction", "KPGH")
    npc.danger_level = kwargs.get("danger_level", 0.7)
    return npc


def make_mock_conversation(role: str, content: str, cycle: int = 1):
    conv = MagicMock()
    conv.role = role
    conv.content = content
    conv.cycle = cycle
    conv.created_at = datetime.now(timezone.utc)
    return conv


_SENTINEL = object()  # маркер "аргумент не передан"


def setup_basic_mocks(
    mock_db,
    user=_SENTINEL,
    session=_SENTINEL,
    player=_SENTINEL,
    person=_SENTINEL,
    location=_SENTINEL,
    npcs=_SENTINEL,
    conversations=_SENTINEL,
):
    """
    Вспомогательная функция: настраивает mock_db.execute и mock_db.get
    для типового сценария.

    - Аргумент не передан -> дефолтный мок
    - Аргумент передан как None -> запрос вернёт None (например, пользователь не найден)
    """
    mock_user = make_mock_user() if user is _SENTINEL else user
    mock_session = make_mock_session() if session is _SENTINEL else session
    mock_player = make_mock_player() if player is _SENTINEL else player

    # Стандартный результат для execute().scalar_one_or_none()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.side_effect = [
        mock_user,
        mock_session,
        mock_player,
    ]

    # Стандартный результат для execute().scalars().all()
    scalars_result = MagicMock()

    mock_db.get.return_value = None

    # npcs и conversations: если не переданы — пустой список
    npcs_list = [] if npcs is _SENTINEL else (npcs or [])
    convs_list = [] if conversations is _SENTINEL else (conversations or [])

    call_count = [0]

    def execute_side_effect(*args, **kwargs):
        nonlocal npcs_list, convs_list
        call_count[0] += 1
        call_n = call_count[0]

        if call_n <= 3:
            return scalar_result
        elif call_n == 4:
            scalars_result.scalars.return_value.all.return_value = npcs_list
            return scalars_result
        else:
            scalars_result.scalars.return_value.all.return_value = convs_list
            return scalars_result

    mock_db.execute.side_effect = execute_side_effect

    # Настройка get
    def get_side_effect(model, pk):
        # person не передан (None или _SENTINEL) — пропускаем
        if person is not _SENTINEL and person is not None:
            if hasattr(model, '__name__') and model.__name__ == "Person" and pk == person.id:
                return person
        if location is not _SENTINEL and location is not None:
            if hasattr(model, '__name__') and model.__name__ == "Location" and pk == location.id:
                return location
        return None

    mock_db.get.side_effect = get_side_effect


# ── Успешная загрузка ─────────────────────────────

class TestSuccessfulLoad:
    """Полный сценарий: пользователь есть, сессия есть, данные загружены."""

    def test_loads_all_context(self, mock_db, base_state):
        """Загружает сессию, игрока, локацию, NPC, историю."""
        mock_npc = make_mock_npc(person_id=20)
        mock_npc2 = make_mock_npc(person_id=21, faction="Likvidator", danger_level=0.3)
        make_mock_person(id=20, name="Хромой", current_location_id=100)
        make_mock_person(id=21, name="Дохлый", current_location_id=100)

        mock_npc_person = make_mock_person(id=20, name="Хромой")
        mock_npc_person2 = make_mock_person(id=21, name="Дохлый")

        convs = [
            make_mock_conversation("user", "осмотреться", cycle=7),
            make_mock_conversation("assistant", "Вы в коридоре", cycle=7),
        ]

        setup_basic_mocks(
            mock_db,
            person=make_mock_person(),
            location=make_mock_location(),
            npcs=[mock_npc, mock_npc2],
            conversations=convs,
        )

        # Для NPC db.get возвращает Person по npc.person_id
        def get_side_effect(model, pk):
            if hasattr(model, '__name__'):
                if model.__name__ == "Person" and pk == 10:
                    return make_mock_person()
                if model.__name__ == "Person" and pk == 20:
                    return mock_npc_person
                if model.__name__ == "Person" and pk == 21:
                    return mock_npc_person2
                if model.__name__ == "Location" and pk == 100:
                    return make_mock_location()
            return None
        mock_db.get.side_effect = get_side_effect

        result = load_memory(base_state, mock_db)

        assert result.error is None
        assert result.session_id == 42
        assert result.player_id == 10
        assert result.current_location_id == 100
        assert result.current_location_name == "Коридор секции Б"
        assert result.current_cycle == 7
        assert result.current_time == "14:30"
        assert result.game_over is False

        assert "npcs_in_location" in result.extra
        assert len(result.extra["npcs_in_location"]) == 2

        assert len(result.memory) == 2
        assert result.memory[0]["role"] == "assistant"
        assert result.memory[1]["role"] == "user"


# ── Пользователь не найден ─────────────────────────

class TestUserNotFound:
    """Если пользователя нет в БД — ошибка."""

    def test_no_user(self, mock_db, base_state):
        """Пользователь с таким chat_id не найден."""
        setup_basic_mocks(mock_db, user=None)

        result = load_memory(base_state, mock_db)

        assert result.error is not None
        assert "пользователь не найден" in result.error.lower()


# ── Нет сессии ────────────────────────────────────

class TestNoSession:
    """Если нет активной сессии — ошибка."""

    def test_no_active_session(self, mock_db, base_state):
        """Пользователь есть, но нет ни одной сессии."""
        setup_basic_mocks(mock_db, session=None)

        result = load_memory(base_state, mock_db)

        assert result.error is not None
        assert "сессии" in result.error.lower()


# ── Игра завершена ─────────────────────────────────

class TestGameOver:
    """Если игра завершена — не загружаем дальше."""

    def test_game_over_stops_loading(self, mock_db, base_state):
        """game_over=True — возвращаем сразу, не ищем игрока."""
        mock_session = make_mock_session(game_over=True)
        setup_basic_mocks(mock_db, session=mock_session)

        result = load_memory(base_state, mock_db)

        assert result.error is None  # не ошибка, просто game_over
        assert result.game_over is True
        assert result.player_id is None  # игрок не загружался


# ── Нет персонажа ──────────────────────────────────

class TestNoPlayer:
    """Если Player не создан — ошибка."""

    def test_no_player_character(self, mock_db, base_state):
        """Сессия есть, но персонаж не создан."""
        setup_basic_mocks(mock_db, player=None)

        result = load_memory(base_state, mock_db)

        assert result.error is not None
        assert "персонаж" in result.error.lower()


# ── Без локации ──────────────────────────────────

class TestNoLocation:
    """Персонаж без локации — не падаем, просто без неё."""

    def test_no_current_location(self, mock_db, base_state):
        """У персонажа нет current_location_id — не падаем."""
        person_no_loc = make_mock_person(current_location_id=None)
        setup_basic_mocks(mock_db, person=person_no_loc)

        result = load_memory(base_state, mock_db)

        assert result.error is None
        assert result.current_location_id is None
        assert result.current_location_name is None


# ── Пустая история ────────────────────────────────

class TestEmptyHistory:
    """Нет сообщений в истории — не падаем."""

    def test_empty_conversation_history(self, mock_db, base_state):
        """История диалога пуста — memory пустой список."""
        setup_basic_mocks(
            mock_db,
            person=make_mock_person(),
            location=make_mock_location(),
            npcs=[],
            conversations=[],
        )

        result = load_memory(base_state, mock_db)

        assert result.error is None
        assert result.memory == []


# ── Забаненный пользователь ───────────────────────

class TestBannedUser:
    """Забаненный пользователь — is_allowed=False."""

    def test_banned_user(self, mock_db, base_state):
        """Пользователь с is_allowed=False."""
        mock_user = make_mock_user(is_allowed=False)
        setup_basic_mocks(mock_db, user=mock_user)

        result = load_memory(base_state, mock_db)

        assert result.is_allowed is False


