# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Update State Node
# ─────────────────────────────────────────────────

"""
Сохранение результатов хода в БД.

Обновляет:
  - История диалога (Conversation)
  - Локация игрока (если изменилась)
  - ID локации (если передан location_id)
  - Инвентарь (если есть items)
  - Квесты (если есть quests)
  - game_over (если true)
  - Цикл (инкремент)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from bot.models.conversation import Conversation
from bot.models.location import Location
from bot.models.person import Person
from bot.models.session import GameSession
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)


# ── Update State ──────────────────────────────────

def update_state(state: GameState, db: Session) -> GameState:
    """
    Сохраняет результаты хода в БД.

    Args:
        state: GameState с parsed_response
        db: Сессия SQLAlchemy

    Returns:
        GameState с обновлённым current_cycle и локацией
    """
    if not state.session_id:
        state.error = "Нет session_id — нечего сохранять."
        logger.warning("UpdateState: нет session_id для chat_id=%s", state.chat_id)
        return state

    action = state.parsed_response
    if not action:
        logger.debug("UpdateState: нет parsed_response, пропускаем сохранение")
        return state

    logger.info("UpdateState: сохранение хода для session_id=%s", state.session_id)

    now = datetime.now(timezone.utc)

    # 1. Сохраняем сообщение пользователя в историю
    user_msg = Conversation(
        session_id=state.session_id,
        role="user",
        content=state.user_input,
        cycle=state.current_cycle,
        tokens_used=0,
    )
    db.add(user_msg)

    # 2. Сохраняем ответ LLM в историю
    assistant_msg = Conversation(
        session_id=state.session_id,
        role="assistant",
        content=action.text,
        cycle=state.current_cycle,
        tokens_used=0,
    )
    db.add(assistant_msg)

    # 3. Обновляем сессию
    game_session = db.get(GameSession, state.session_id)
    if game_session:
        if action.game_over:
            game_session.game_over = True
            logger.info("UpdateState: игра завершена для session_id=%s", state.session_id)

        # Инкремент цикла
        game_session.current_cycle = (game_session.current_cycle or 0) + 1
        state.current_cycle = game_session.current_cycle

        # Обновляем время (+1 час каждый ход)
        current_hour = int(state.current_time.split(":")[0])
        current_hour = (current_hour + 1) % 24
        game_session.current_time = f"{current_hour:02d}:00"
        state.current_time = game_session.current_time

    # 4. Обновляем локацию игрока
    if action.location and state.player_id:
        person = db.get(Person, state.player_id)
        if person:
            # Ищем локацию по имени (в рамках сессии)
            location = db.query(Location).filter(
                Location.session_id == state.session_id,
                Location.name == action.location,
            ).first()

            if location:
                person.current_location_id = location.id
                state.current_location_id = location.id
                state.current_location_name = action.location
                logger.info("UpdateState: персонаж перемещён в '%s'", action.location)
            elif action.location_id:
                # Если передан location_id — используем его напрямую
                loc = db.get(Location, action.location_id)
                if loc:
                    person.current_location_id = loc.id
                    state.current_location_id = loc.id
                    state.current_location_name = loc.name

    db.commit()

    logger.info("UpdateState: ход сохранён (цикл %d)", state.current_cycle)

    return state