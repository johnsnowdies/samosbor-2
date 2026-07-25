# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Generate World Node
# Генерация игрового мира при /start
# ─────────────────────────────────────────────────

"""
Генерация мира при старте новой игры.

Вызывает LLM со специальным промптом для генерации:
  - Персонажа игрока
  - Этажей
  - Стартовой локации + 2-4 соединённых с ней
  - Связей между локациями
  - NPC
  - Отношений между NPC
  - Стартовых предметов и квестов

Создаёт все сущности в БД.
"""

from __future__ import annotations

import json
import logging
import os
import re

from openai import OpenAI
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.schemas.game import GameState, WorldData, LocationData, NpcData
from bot.schemas.game import FloorData, LocationConnectionData, NpcRelationData
from bot.utils.langfuse_trace import trace_llm_call

logger = logging.getLogger(__name__)

# ── Конфигурация ─────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

WORLD_GEN_PROMPT = """Ты — генератор игрового мира для RPG «Самосбор» (мир Гигахрущёвки).
Сгенерируй стартовую локацию игрока и 2-4 соседних локации, соединённых с ней.

## Сеттинг
Гигахрущёвка — бесконечное здание без окон, с тусклым освещением, неработающими лифтами.
Каждый этаж — свой мир: одни обитаемы, другие заброшены, третьи сожраны Самосбором.

## Твоя задача
1. Создать персонажа игрока (имя, предыстория, внешность, характер, привычки)
2. Создать 1 этаж для стартовой зоны
3. Создать стартовую локацию + 2-4 соединённых с ней локации на том же этаже
4. Создать связи между локациями (тип перехода, описание)
5. Создать 1-3 NPC в этих локациях
6. Создать отношения между NPC (если NPC > 1)
7. Дать стартовые предметы и квест

## Стиль
- Имена NPC: используй имиджборд-юмор (бабка Срака, дядя Толя, тётя Ячмись-сыночка-корзиночка, Хмырь, Шнырь, Лысый)
- Названия локаций: мрачные, бытовые («Захламлённая прихожая», «Бывшая прачечная», «Комната 312», «Тёмный коридор»)
- Предметы: ржавые, сломанные, бесполезные на первый взгляд (ржавый ключ, погнутая вилка, пустая банка, промасленная тряпка)
- Атмосфера: безысходность, упадок, опасность

## JSON ответ
Только JSON, без пояснений:
```json
{
  "player_name": "Имя",
  "player_bio": "Предыстория 2-3 предложения",
  "player_appearance": "Внешность",
  "player_personality": "Характер",
  "player_habits": "Привычки",
  "floors": [{"name": "Название этажа", "danger_level": 0.3, "is_contaminated": false}],
  "start_location": "Название стартовой локации",
  "start_location_description": "Описание",
  "locations": [
    {"name": "Стартовая локация", "description": "Описание", "floor": "Название этажа"},
    {"name": "Соседняя локация 1", "description": "Описание", "floor": "Название этажа"}
  ],
  "connections": [
    {"from_location": "Стартовая локация", "to_location": "Соседняя локация 1",
     "description": "Дверь с облупившейся краской", "transition_type": "door", "is_locked": false}
  ],
  "items": ["предмет 1", "предмет 2"],
  "npcs": [
    {"name": "Имя", "bio": "Кто это", "personality": "Характер",
     "appearance": "Внешность", "habits": "Привычки",
     "faction": "Фракция", "danger_level": 0.0, "location": "Название локации"}
  ],
  "npc_relations": [
    {"npc_name_from": "NPC 1", "npc_name_to": "NPC 2", "affinity": 0.5}
  ],
  "quests": ["Стартовый квест"]
}
```"""


# ── Клиент ───────────────────────────────────────


_retry_decorator = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


@_retry_decorator
def _call_llm(prompt: str) -> str:
    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM вернул пустой ответ")
    logger.info("GenerateWorld: ответ получен (%d символов)", len(content))
    return content.strip()


def _extract_json(text: str) -> dict | None:
    """Извлекает JSON из ответа LLM."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    json_str = match.group(1).strip() if match else text.strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            try:
                return json.loads(brace.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _create_world_in_db(state: GameState, world: WorldData, db) -> GameState:
    """Создаёт все сущности мира в БД."""
    from sqlalchemy import select
    from bot.models.floor import Floor
    from bot.models.location import Location, LocationConnection
    from bot.models.person import Person
    from bot.models.player import Player
    from bot.models.npc import NPC
    from bot.models.item import Item
    from bot.models.task import Task
    from bot.models.social import SocialRelation

    logger.info("GenerateWorld: создание мира для session_id=%s", state.session_id)

    from bot.models.session import GameSession
    sess = db.get(GameSession, state.session_id)
    if not sess:
        state.error = "Сессия не найдена"
        return state

    try:
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

        if not floor_map:
            floor = Floor(session_id=state.session_id, name="Этаж 1", danger_level=0.3)
            db.add(floor)
            db.flush()
            floor_map["Этаж 1"] = floor

        # 2. Все локации
        location_map: dict[str, Location] = {}
        all_locations = list(world.locations)
        if not any(l.name == world.start_location for l in all_locations):
            all_locations.insert(0, LocationData(
                name=world.start_location,
                description=world.start_location_description,
                floor=next(iter(floor_map.keys())),
            ))

        for ld in all_locations:
            floor_name = ld.floor or next(iter(floor_map.keys()))
            floor_id = floor_map.get(floor_name, next(iter(floor_map.values()))).id
            loc = Location(
                session_id=state.session_id,
                floor_id=floor_id,
                name=ld.name,
                description=ld.description or "",
            )
            db.add(loc)
            db.flush()
            location_map[ld.name] = loc

        logger.info("GenerateWorld: создано %d локаций", len(location_map))

        # 3. Связи между локациями
        for cd in world.connections:
            from_loc = location_map.get(cd.from_location)
            to_loc = location_map.get(cd.to_location)
            if from_loc and to_loc and from_loc.id != to_loc.id:
                existing = db.execute(
                    select(LocationConnection).where(
                        LocationConnection.from_location_id == from_loc.id,
                        LocationConnection.to_location_id == to_loc.id,
                    )
                ).first()
                if not existing:
                    db.add(LocationConnection(
                        from_location_id=from_loc.id,
                        to_location_id=to_loc.id,
                        session_id=state.session_id,
                        description=cd.description,
                        transition_type=cd.transition_type,
                        is_locked=cd.is_locked,
                    ))
                    db.add(LocationConnection(
                        from_location_id=to_loc.id,
                        to_location_id=from_loc.id,
                        session_id=state.session_id,
                        description=f"Обратно: {cd.description}",
                        transition_type=cd.transition_type,
                        is_locked=cd.is_locked,
                    ))

        # 4. Персонаж игрока
        start_loc = location_map.get(world.start_location) or next(iter(location_map.values()))

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

        player = Player(person_id=person.id, session_id=state.session_id)
        db.add(player)
        db.flush()

        state.player_id = person.id
        state.current_location_id = start_loc.id
        state.current_location_name = world.start_location

        # Сохраняем данные персонажа для build_prompt
        state.extra["player_name"] = world.player_name
        state.extra["player_bio"] = world.player_bio
        state.extra["player_appearance"] = world.player_appearance
        state.extra["player_personality"] = world.player_personality

        logger.info("GenerateWorld: персонаж '%s' создан", world.player_name)

        # 5. NPC
        npc_name_to_id: dict[str, int] = {}
        for nd in world.npcs:
            npc_loc = location_map.get(nd.location or "") or start_loc
            npc_person = Person(
                session_id=state.session_id,
                name=nd.name,
                bio=nd.bio,
                personality=nd.personality,
                appearance=nd.appearance,
                habits=nd.habits,
                current_location_id=npc_loc.id,
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

        # 6. Отношения
        for rd in world.npc_relations:
            from_id = npc_name_to_id.get(rd.npc_name_from)
            to_id = npc_name_to_id.get(rd.npc_name_to)
            if from_id and to_id and from_id != to_id:
                db.add(SocialRelation(
                    session_id=state.session_id,
                    from_person_id=from_id,
                    to_person_id=to_id,
                    affinity=rd.affinity,
                ))

        # 7. Предметы
        for item_name in world.items:
            db.add(Item(
                session_id=state.session_id,
                owner_id=person.id,
                location_id=start_loc.id,
                item_type="misc",
                name=item_name,
            ))

        # 8. Квесты
        for quest_desc in world.quests:
            db.add(Task(
                session_id=state.session_id,
                assignee_id=person.id,
                location_id=start_loc.id,
                is_completed=False,
                title=quest_desc[:128],
                summary=quest_desc,
            ))

        db.commit()
        logger.info("GenerateWorld: мир создан: %d этажей, %d локаций, %d NPC, %d предметов, %d квестов",
                     len(floor_map), len(location_map), len(world.npcs), len(world.items), len(world.quests))

    except Exception as e:
        db.rollback()
        logger.error("GenerateWorld: ошибка создания мира: %s", e)
        state.error = f"Ошибка генерации мира: {e}"

    return state


# ── Node ──────────────────────────────────────────

def generate_world(state: GameState, db) -> GameState:
    """
    Генерирует мир при /start.

    Вызывает LLM, парсит ответ, создаёт сущности в БД.

    Args:
        state: GameState с session_id
        db: SQLAlchemy сессия (не используется, т.к. каждая нода своя)

    Returns:
        GameState с player_id, current_location_id
    """
    logger.info("GenerateWorld: старт для chat_id=%s", state.chat_id)

    if not state.session_id:
        state.error = "Нет session_id."
        return state

    try:
        response = _call_llm(WORLD_GEN_PROMPT)
    except Exception as e:
        state.error = f"Ошибка вызова LLM: {e}"
        return state

    data = _extract_json(response)
    if not data:
        state.error = "Не удалось распарсить ответ LLM"
        return state

    try:
        world = WorldData(**data)
    except Exception as e:
        state.error = f"Ошибка валидации WorldData: {e}"
        return state

    state = _create_world_in_db(state, world, db)

    return state