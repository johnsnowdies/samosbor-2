# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Memory Node
# ─────────────────────────────────────────────────

"""
Загрузка контекста из БД.

Поднимает в GameState:
  - Сессию игрока (session_id, game_over, current_cycle, current_time)
  - Текущую локацию
  - NPC в той же локации
  - Последние N сообщений из истории диалога
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.models.conversation import Conversation
from bot.models.location import Location
from bot.models.npc import NPC
from bot.models.person import Person
from bot.models.player import Player
from bot.models.session import GameSession
from bot.models.user import User
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)

# ── Константы ─────────────────────────────────────

MAX_HISTORY_MESSAGES = 20  # сколько последних сообщений подгружать


# ── Memory ─────────────────────────────────────────

def load_memory(state: GameState, db: Session) -> GameState:
    """
    Загружает контекст из БД и заполняет GameState.

    Args:
        state: Текущее состояние (должен быть chat_id)
        db: Сессия SQLAlchemy

    Returns:
        GameState с заполненными полями контекста
    """
    logger.info("Memory: загрузка контекста для chat_id=%s", state.chat_id)

    # 1. Пользователь
    user = db.execute(
        select(User).where(User.telegram_chat_id == state.chat_id)
    ).scalar_one_or_none()

    if user is None:
        state.error = "Пользователь не найден. Начните с /start."
        logger.warning("Memory: пользователь chat_id=%s не найден", state.chat_id)
        return state

    state.is_allowed = user.is_allowed

    # 2. Активная игровая сессия
    session = db.execute(
        select(GameSession)
        .where(
            GameSession.user_id == user.id,
            GameSession.game_over == False,
        )
        .order_by(GameSession.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if session is None:
        state.error = "Нет активной игровой сессии. Начните новую игру с /start."
        logger.warning("Memory: нет сессии для chat_id=%s", state.chat_id)
        return state

    state.session_id = session.id
    state.game_over = session.game_over
    state.current_cycle = session.current_cycle
    state.current_time = session.current_time

    if state.game_over:
        logger.info("Memory: игра завершена для chat_id=%s", state.chat_id)
        return state

    # 3. Игрок (Player → Person)
    player = db.execute(
        select(Player).where(Player.session_id == session.id)
    ).scalar_one_or_none()

    if player is None:
        state.error = "Персонаж не найден. Начните новую игру."
        logger.warning("Memory: нет персонажа для session_id=%s", session.id)
        return state

    state.player_id = player.person_id

    # 4. Текущая локация
    person = db.get(Person, player.person_id)
    if person and person.current_location_id:
        location = db.get(Location, person.current_location_id)
        if location:
            state.current_location_id = location.id
            state.current_location_name = location.name

    # 5. NPC в той же локации + описание локации
    if state.current_location_id:
        loc_obj = db.get(Location, state.current_location_id)
        if loc_obj:
            state.extra["location_description"] = loc_obj.description or ""

        npcs_in_location = db.execute(
            select(NPC)
            .join(Person, NPC.person_id == Person.id)
            .where(
                Person.current_location_id == state.current_location_id,
                Person.session_id == session.id,
                NPC.person_id != player.person_id,
            )
        ).scalars().all()

        state.extra["npcs_in_location"] = [
            {
                "id": npc.person_id,
                "name": db.get(Person, npc.person_id).name if db.get(Person, npc.person_id) else "Unknown",
                "faction": npc.faction,
                "danger_level": npc.danger_level,
            }
            for npc in npcs_in_location
        ]

    # 6. Инвентарь игрока
    if state.player_id:
        from bot.models.item import Item
        items = db.execute(
            select(Item).where(
                Item.owner_id == state.player_id,
                Item.session_id == session.id,
            )
        ).scalars().all()
        state.extra["player_inventory"] = [item.name for item in items]

    # 7. Социальные отношения между NPC в этой локации
    npcs_in_loc = state.extra.get("npcs_in_location", [])
    if npcs_in_loc and len(npcs_in_loc) > 1:
        from bot.models.social import SocialRelation
        npc_ids = [n["id"] for n in npcs_in_loc]
        relations = db.execute(
            select(SocialRelation).where(
                SocialRelation.session_id == session.id,
                SocialRelation.from_person_id.in_(npc_ids),
                SocialRelation.to_person_id.in_(npc_ids),
            )
        ).scalars().all()

        if relations:
            npc_name_map = {n["id"]: n["name"] for n in npcs_in_loc}
            formatted = []
            for r in relations:
                from_name = npc_name_map.get(r.from_person_id, f"NPC #{r.from_person_id}")
                to_name = npc_name_map.get(r.to_person_id, f"NPC #{r.to_person_id}")
                formatted.append({
                    "from": from_name,
                    "to": to_name,
                    "affinity": r.affinity,
                })
            state.extra["npc_relations"] = formatted

    # 8. История диалога (последние N сообщений)
    conversations = db.execute(
        select(Conversation)
        .where(Conversation.session_id == session.id)
        .order_by(Conversation.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
    ).scalars().all()

    # Переворачиваем в хронологическом порядке
    state.memory = [
        {"role": c.role, "content": c.content, "cycle": c.cycle}
        for c in reversed(conversations)
    ]

    logger.info(
        "Memory: загружено session_id=%s, локация=%s, NPC=%d, сообщений=%d",
        state.session_id,
        state.current_location_name,
        len(state.extra.get("npcs_in_location", [])),
        len(state.memory),
    )

    return state