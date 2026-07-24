# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Update State Node
# ─────────────────────────────────────────────────

"""
Сохранение результатов хода в БД.

Обновляет:
  - История диалога (Conversation)
  - Локация игрока (если изменилась)
  - Инвентарь (если есть items)
  - Квесты (если есть quests)
  - game_over (если true)
  - Цикл (инкремент)
  + При /start — создание мира (Person, Player, Floor, Location, NPC, Item, Task)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from bot.models.conversation import Conversation
from bot.models.floor import Floor
from bot.models.item import Item
from bot.models.location import Location
from bot.models.npc import NPC
from bot.models.person import Person
from bot.models.player import Player
from bot.models.session import GameSession
from bot.models.social import SocialRelation
from bot.models.task import Task
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)


# ── Создание мира при /start ──────────────────────

def _create_world(state: GameState, db: Session, game_session: GameSession) -> GameState:
    """Создаёт игровой мир из WorldData: этажи, локации, персонажа, NPC, предметы, квесты."""
    from bot.schemas.game import WorldData

    world = state.parsed_response.world
    if not world:
        logger.warning("CreateWorld: нет world данных в ответе LLM")
        return state

    logger.info("CreateWorld: создание мира для session_id=%s", state.session_id)

    # 1. Этажи
    floor_map: dict[str, Floor] = {}
    for fd in world.floors:
        floor = Floor(
            session_id=state.session_id,
            name=fd.name,
            danger_level=fd.danger_level,
            is_contaminated=fd.is_contaminated,
        )
        db.add(floor)
        db.flush()
        floor_map[fd.name] = floor
        logger.debug("CreateWorld: этаж '%s' создан (id=%s)", fd.name, floor.id)

    # Если этажей нет — создаём дефолтный
    if not floor_map:
        floor = Floor(
            session_id=state.session_id,
            name="Этаж 1",
            danger_level=0.3,
            is_contaminated=False,
        )
        db.add(floor)
        db.flush()
        floor_map["Этаж 1"] = floor

    # 2. Локации (стартовая + все, где указаны NPC)
    location_map: dict[str, Location] = {}

    # Стартовая локация
    start_floor_name = next(iter(floor_map.keys()), "Этаж 1")
    start_loc = Location(
        session_id=state.session_id,
        floor_id=floor_map[start_floor_name].id,
        name=world.start_location,
        description=world.start_location_description,
    )
    db.add(start_loc)
    db.flush()
    location_map[world.start_location] = start_loc
    logger.info("CreateWorld: стартовая локация '%s' (id=%s)", world.start_location, start_loc.id)

    # Локации NPC
    for nd in world.npcs:
        if nd.location and nd.location not in location_map:
            # Определяем этаж для этой локации
            npc_floor_name = start_floor_name
            if nd.location != world.start_location:
                # Ищем этаж, который может содержать эту локацию
                for fn in floor_map:
                    if fn.lower() in nd.location.lower() or nd.location.lower().startswith(fn.lower().split()[0]):
                        npc_floor_name = fn
                        break

            loc = Location(
                session_id=state.session_id,
                floor_id=floor_map.get(npc_floor_name, start_loc.floor_id),
                name=nd.location,
                description=f"Локация: {nd.location}",
            )
            db.add(loc)
            db.flush()
            location_map[nd.location] = loc
            logger.debug("CreateWorld: локация NPC '%s' (id=%s)", nd.location, loc.id)

    db.flush()

    # 3. Персонаж игрока (Person + Player)
    person = Person(
        session_id=state.session_id,
        name=world.player_name,
        bio=world.player_bio,
        personality=world.player_personality,
        appearance=world.player_appearance,
        habits=world.player_habits,
        current_location_id=start_loc.id,
    )
    db.add(person)
    db.flush()

    player = Player(
        person_id=person.id,
        session_id=state.session_id,
    )
    db.add(player)
    db.flush()

    state.player_id = person.id
    state.current_location_id = start_loc.id
    state.current_location_name = world.start_location

    logger.info("CreateWorld: персонаж '%s' создан (person_id=%s)", world.player_name, person.id)

    # 4. NPC
    npc_name_to_id: dict[str, int] = {}
    for nd in world.npcs:
        npc_loc_id = location_map.get(nd.location, start_loc).id if nd.location else start_loc.id

        npc_person = Person(
            session_id=state.session_id,
            name=nd.name,
            bio=nd.bio,
            personality=nd.personality,
            appearance=nd.appearance,
            habits=nd.habits,
            current_location_id=npc_loc_id,
        )
        db.add(npc_person)
        db.flush()

        npc = NPC(
            person_id=npc_person.id,
            session_id=state.session_id,
            faction=nd.faction,
            danger_level=nd.danger_level,
        )
        db.add(npc)
        db.flush()

        npc_name_to_id[nd.name] = npc_person.id
        logger.debug("CreateWorld: NPC '%s' создан (person_id=%s)", nd.name, npc_person.id)

    # 5. Отношения между NPC
    for rd in world.npc_relations:
        from_id = npc_name_to_id.get(rd.npc_name_from)
        to_id = npc_name_to_id.get(rd.npc_name_to)
        if from_id and to_id and from_id != to_id:
            relation = SocialRelation(
                session_id=state.session_id,
                from_person_id=from_id,
                to_person_id=to_id,
                affinity=rd.affinity,
            )
            db.add(relation)
            logger.debug("CreateWorld: отношение %s -> %s (affinity=%.1f)",
                         rd.npc_name_from, rd.npc_name_to, rd.affinity)

    # 6. Стартовые предметы
    for item_name in world.items:
        item = Item(
            session_id=state.session_id,
            owner_id=person.id,
            location_id=start_loc.id,
            item_type="general",
            name=item_name,
        )
        db.add(item)
        logger.debug("CreateWorld: предмет '%s' создан", item_name)

    # 7. Стартовые квесты
    for quest_desc in world.quests:
        task = Task(
            session_id=state.session_id,
            assignee_id=person.id,
            location_id=start_loc.id,
            is_completed=False,
            title=quest_desc[:128],
            summary=quest_desc,
        )
        db.add(task)
        logger.debug("CreateWorld: квест '%s' создан", quest_desc[:50])

    db.commit()
    logger.info("CreateWorld: мир создан: %d этажей, %d локаций, %d NPC, %d предметов, %d квестов",
                len(floor_map), len(location_map), len(world.npcs), len(world.items), len(world.quests))

    return state


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

    game_session = db.get(GameSession, state.session_id)
    if not game_session:
        state.error = "Сессия не найдена."
        return state

    # ── Если есть world данные — создаём мир (при /start) ──
    if action.world is not None and state.player_id is None:
        state = _create_world(state, db, game_session)
        if state.error:
            return state

    # 1. Сохраняем сообщение пользователя
    from bot.utils import clean_str
    user_msg = Conversation(
        session_id=state.session_id,
        role="user",
        content=clean_str(state.user_input),
        cycle=state.current_cycle,
        tokens_used=0,
    )
    db.add(user_msg)

    # 2. Сохраняем ответ LLM
    assistant_msg = Conversation(
        session_id=state.session_id,
        role="assistant",
        content=clean_str(action.text),
        cycle=state.current_cycle,
        tokens_used=0,
    )
    db.add(assistant_msg)

    # 3. Обновляем сессию
    if action.game_over:
        game_session.game_over = True
        logger.info("UpdateState: игра завершена для session_id=%s", state.session_id)

    # Инкремент цикла
    game_session.current_cycle = (game_session.current_cycle or 0) + 1
    state.current_cycle = game_session.current_cycle

    # Обновляем время (+1 час)
    current_hour = int(state.current_time.split(":")[0])
    current_hour = (current_hour + 1) % 24
    game_session.current_time = f"{current_hour:02d}:00"
    state.current_time = game_session.current_time

    # 4. Обновляем локацию игрока
    if action.location and state.player_id:
        person = db.get(Person, state.player_id)
        if person:
            location = db.query(Location).filter(
                Location.session_id == state.session_id,
                Location.name == action.location,
            ).first()

            if location:
                old_location_id = state.current_location_id
                old_floor_id = None
                if old_location_id:
                    old_loc = db.get(Location, old_location_id)
                    if old_loc:
                        old_floor_id = old_loc.floor_id

                person.current_location_id = location.id
                state.current_location_id = location.id
                state.current_location_name = action.location
                state.location_changed = (old_location_id != location.id)

                # Проверяем смену этажа
                if state.location_changed and old_floor_id is not None:
                    state.floor_changed = (old_floor_id != location.floor_id)

                logger.info("UpdateState: персонаж перемещён в '%s' (location_changed=%s, floor_changed=%s)",
                            action.location, state.location_changed, state.floor_changed)
            elif action.location_id:
                loc = db.get(Location, action.location_id)
                if loc:
                    old_location_id = state.current_location_id
                    old_floor_id = None
                    if old_location_id:
                        old_loc = db.get(Location, old_location_id)
                        if old_loc:
                            old_floor_id = old_loc.floor_id

                    person.current_location_id = loc.id
                    state.current_location_id = loc.id
                    state.current_location_name = loc.name
                    state.location_changed = (old_location_id != loc.id)

                    if state.location_changed and old_floor_id is not None:
                        state.floor_changed = (old_floor_id != loc.floor_id)

    # 5. Обработка предметов (если не /start, где уже создали)
    if action.world is None and action.items and state.player_id:
        for item_name in action.items:
            item = Item(
                session_id=state.session_id,
                owner_id=state.player_id,
                location_id=state.current_location_id,
                item_type="general",
                name=item_name,
            )
            db.add(item)

    # 6. Обработка квестов (если не /start)
    if action.world is None and action.quests and state.player_id:
        for quest_desc in action.quests:
            task = Task(
                session_id=state.session_id,
                assignee_id=state.player_id,
                location_id=state.current_location_id,
                is_completed=False,
                title=quest_desc[:128],
                summary=quest_desc,
            )
            db.add(task)

    # 7. Обработка изменений отношений
    if action.world is None and action.social_changes:
        from sqlalchemy import select
        from bot.models.social import SocialRelation

        for sc in action.social_changes:
            # Ищем NPC по имени
            npc_person = db.execute(
                select(Person).where(
                    Person.session_id == state.session_id,
                    Person.name == sc.npc,
                )
            ).scalar_one_or_none()
            if not npc_person:
                logger.warning("SocialChange: NPC '%s' не найден", sc.npc)
                continue

            # Определяем target: "игрок" → person.id, иначе NPC по имени
            if sc.target.lower() == "игрок":
                target_id = state.player_id
            else:
                target_person = db.execute(
                    select(Person).where(
                        Person.session_id == state.session_id,
                        Person.name == sc.target,
                    )
                ).scalar_one_or_none()
                if not target_person:
                    logger.warning("SocialChange: цель '%s' не найдена", sc.target)
                    continue
                target_id = target_person.id

            if not target_id or npc_person.id == target_id:
                continue

            # Ищем существующее отношение
            relation = db.execute(
                select(SocialRelation).where(
                    SocialRelation.session_id == state.session_id,
                    SocialRelation.from_person_id == npc_person.id,
                    SocialRelation.to_person_id == target_id,
                )
            ).scalar_one_or_none()

            if relation:
                new_affinity = max(-1.0, min(1.0, relation.affinity + sc.delta))
                relation.affinity = new_affinity
                logger.info("SocialChange: %s → %s: изменено (дельта=%.1f, %s)",
                            sc.npc, sc.target, sc.delta, sc.reason)
            else:
                relation = SocialRelation(
                    session_id=state.session_id,
                    from_person_id=npc_person.id,
                    to_person_id=target_id,
                    affinity=max(-1.0, min(1.0, sc.delta)),
                )
                db.add(relation)
                logger.info("SocialChange: %s → %s: создано (дельта=%.1f, %s)",
                            sc.npc, sc.target, sc.delta, sc.reason)

    db.commit()

    logger.info("UpdateState: ход сохранён (цикл %d)", state.current_cycle)

    return state