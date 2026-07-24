# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Start Game Node
# ─────────────────────────────────────────────────

"""
Обработка команды /start — начало новой игры.

1. Проверяет/создаёт пользователя
2. Завершает старую сессию, создаёт новую
3. Формирует специальный промпт для генерации персонажа
   и стартовой сцены
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.models.location import Location
from bot.models.player import Player
from bot.models.person import Person
from bot.models.session import GameSession
from bot.models.user import User
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)

# ── Стартовый промпт ──────────────────────────────

START_PROMPT = """Ты — мастер игры «Самосбор». Сгенерируй начало новой игры.

## Новая игра
Игрок только что вошёл в мир Гигахрущёвки. Твоя задача:
1. Создать персонажа игрока: имя, внешность, предыстория (2-3 предложения)
2. Описать стартовую локацию: этаж, комната, обстановка
3. Дать первый квест
4. Описать, что игрок видит, слышит и чувствует

## JSON ответ
```json
{
  "text": "Вступительное описание — кто ты, где ты, что вокруг. 3-5 предложений.",
  "actions": ["первое действие", "второе действие", "третье действие", "четвёртое действие"],
  "items": ["стартовый предмет 1", "стартовый предмет 2"],
  "quests": ["первый квест"],
  "location": "название стартовой локации",
  "game_over": false,
  "image_prompt": "описание стартовой сцены на английском"
}
```"""


# ── Start Game ─────────────────────────────────────

def start_game(state: GameState, db: Session) -> GameState:
    """
    Обрабатывает команду /start.

    Args:
        state: Состояние с chat_id и user_input (ожидается "/start")
        db: Сессия SQLAlchemy

    Returns:
        GameState с готовым промптом для генерации начала игры
    """
    logger.info("Start game: начало новой игры для chat_id=%s", state.chat_id)

    # 1. Находим или создаём пользователя
    user = db.execute(
        select(User).where(User.telegram_chat_id == state.chat_id)
    ).scalar_one_or_none()

    if user is None:
        user = User(
            telegram_chat_id=state.chat_id,
            balance=0,
            trial_messages_left=5,
            is_admin=False,
            is_allowed=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Start game: создан новый пользователь id=%s", user.id)

    state.is_allowed = user.is_allowed
    if not state.is_allowed:
        state.error = "Доступ запрещён. Обратитесь к администратору."
        return state

    # 2. Завершаем старую сессию, если есть активная
    old_session = db.execute(
        select(GameSession)
        .where(GameSession.user_id == user.id, GameSession.game_over == False)
        .order_by(GameSession.created_at.desc())
    ).scalar_one_or_none()

    if old_session:
        old_session.game_over = True
        db.commit()
        logger.info("Start game: завершена старая сессия id=%s", old_session.id)

    # 3. Создаём новую сессию
    new_session = GameSession(
        user_id=user.id,
        game_over=False,
        current_cycle=1,
        current_time="08:00",
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    state.session_id = new_session.id
    state.game_over = False
    state.current_cycle = 1
    state.current_time = "08:00"
    state.player_id = None

    # 4. Ставим специальный промпт для генерации начала
    state.prompt = START_PROMPT

    logger.info("Start game: создана новая сессия id=%s", new_session.id)

    return state