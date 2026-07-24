# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Generate Locations Node
# Догенерация локаций при перемещении игрока
# ─────────────────────────────────────────────────

"""
Генерация новых локаций при перемещении игрока в неизвестную локацию.

При смене локации LLM генерирует 2-3 соседних локации + связи.
Создаёт их в БД и фиксирует переход.
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

from bot.schemas.game import GameState
from bot.utils import get_openai_client

logger = logging.getLogger(__name__)

# ── Конфигурация ─────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

LOCATION_GEN_PROMPT = """Ты — генератор локаций для RPG «Самосбор» (мир Гигахрущёвки).
Игрок только что вошёл в новую локацию. Сгенерируй 2-3 соседних локации,
соединённых с ней, и возможных NPC в них.

## Контекст
Текущая локация игрока: {current_location}
Описание: {current_description}
Этаж: {floor_name}
Цикл: {cycle}, время: {time}

## Правила
- Локации должны быть на том же этаже (если не указано иное)
- Связи между локациями: двери, коридоры, лестницы, вентиляция, люки
- NPC могут быть в любых локациях (не обязательно в текущей)
- Сеттинг: Гигахрущёвка, мрачный постапокалипсис
- Имена NPC: имиджборд-юмор (бабка Срака, дядя Толя, Хмырь, Шнырь)
- Названия локаций: бытовые и мрачные («Комната 312», «Захламлённый коридор», «Бывшая столовая»)
- Предметы: ржавые, сломанные, бесполезные на первый взгляд

## JSON ответ
Только JSON, без пояснений:
```json
{{
  "locations": [
    {{"name": "Название локации", "description": "Описание", "floor": "Название этажа"}}
  ],
  "connections": [
    {{"from_location": "Текущая локация", "to_location": "Новая локация",
      "description": "Описание перехода", "transition_type": "door", "is_locked": false}}
  ],
  "npcs": [
    {{"name": "Имя", "bio": "Кто это", "personality": "Характер",
      "appearance": "Внешность", "habits": "Привычки",
      "faction": "Фракция", "danger_level": 0.0, "location": "Название локации"}}
  ]
}}
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
    client = get_openai_client()
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2048,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM вернул пустой ответ")
    return content.strip()


def _extract_json(text: str) -> dict | None:
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


def _create_locations_in_db(state: GameState, data: dict, db) -> GameState:
    """Создаёт новые локации, связи и NPC в БД."""
    from sqlalchemy import select
    from bot.models.floor import Floor
    from bot.models.location import Location, LocationConnection
    from bot.models.person import Person
    from bot.models.npc import NPC
    from bot.models.social import SocialRelation

    try:
        # Определяем текущий этаж
        current_floor_id = None
        if state.current_location_id:
            current_loc = db.get(Location, state.current_location_id)
            if current_loc:
                current_floor_id = current_loc.floor_id

        # Находим или создаём этаж
        floor_name = (data.get("locations") or [{}])[0].get("floor", "")
        floor = None
        if current_floor_id:
            floor = db.get(Floor, current_floor_id)
        if not floor and floor_name:
            floor = db.execute(
                select(Floor).where(
                    Floor.session_id == state.session_id,
                    Floor.name == floor_name,
                )
            ).scalar_one_or_none()
        if not floor:
            floor = db.execute(
                select(Floor).where(Floor.session_id == state.session_id)
            ).first()
            if not floor:
                floor = Floor(
                    session_id=state.session_id,
                    name=floor_name or "Этаж",
                    danger_level=0.3,
                )
                db.add(floor)
                db.flush()

        # Загружаем существующие локации
        existing_locations = db.execute(
            select(Location).where(Location.session_id == state.session_id)
        ).scalars().all()
        location_map = {loc.name: loc for loc in existing_locations}
        if state.current_location_name and state.current_location_name not in location_map:
            if state.current_location_id:
                loc = db.get(Location, state.current_location_id)
                if loc:
                    location_map[loc.name] = loc

        # Создаём новые локации
        new_locations_count = 0
        for ld in data.get("locations", []):
            name = ld.get("name", "")
            if not name or name in location_map:
                continue
            loc = Location(
                session_id=state.session_id,
                floor_id=floor.id,
                name=name,
                description=ld.get("description", ""),
            )
            db.add(loc)
            db.flush()
            location_map[name] = loc
            new_locations_count += 1

        # Создаём связи
        connections_count = 0
        for cd in data.get("connections", []):
            from_loc = location_map.get(cd.get("from_location", ""))
            to_loc = location_map.get(cd.get("to_location", ""))
            if not from_loc or not to_loc or from_loc.id == to_loc.id:
                continue
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
                    description=cd.get("description", ""),
                    transition_type=cd.get("transition_type", "door"),
                    is_locked=cd.get("is_locked", False),
                ))
                db.add(LocationConnection(
                    from_location_id=to_loc.id,
                    to_location_id=from_loc.id,
                    session_id=state.session_id,
                    description=f"Обратно: {cd.get('description', '')}",
                    transition_type=cd.get("transition_type", "door"),
                    is_locked=cd.get("is_locked", False),
                ))
                connections_count += 1

        # Создаём NPC
        new_npcs_count = 0
        npc_name_to_id = {}
        for nd in data.get("npcs", []):
            name = nd.get("name", "")
            if not name:
                continue
            existing_npc = db.execute(
                select(Person).where(
                    Person.session_id == state.session_id,
                    Person.name == name,
                )
            ).first()
            if existing_npc:
                continue

            npc_loc = location_map.get(nd.get("location", "")) or next(iter(location_map.values()))
            npc_person = Person(
                session_id=state.session_id,
                name=name,
                bio=nd.get("bio", ""),
                personality=nd.get("personality", ""),
                appearance=nd.get("appearance", ""),
                habits=nd.get("habits", ""),
                current_location_id=npc_loc.id,
            )
            db.add(npc_person)
            db.flush()
            npc = NPC(
                person_id=npc_person.id,
                session_id=state.session_id,
                faction=nd.get("faction"),
                danger_level=nd.get("danger_level", 0.0),
            )
            db.add(npc)
            db.flush()
            npc_name_to_id[name] = npc_person.id
            new_npcs_count += 1

        # Отношения для новых NPC
        for rd in data.get("npc_relations", []):
            from_id = npc_name_to_id.get(rd.get("npc_name_from", ""))
            to_id = npc_name_to_id.get(rd.get("npc_name_to", ""))
            if from_id and to_id and from_id != to_id:
                db.add(SocialRelation(
                    session_id=state.session_id,
                    from_person_id=from_id,
                    to_person_id=to_id,
                    affinity=rd.get("affinity", 0.0),
                ))

        db.commit()
        logger.info("GenerateLocations: создано %d локаций, %d связей, %d NPC",
                     new_locations_count, connections_count, new_npcs_count)

    except Exception as e:
        db.rollback()
        logger.error("GenerateLocations: ошибка: %s", e)

    return state


# ── Node ──────────────────────────────────────────

def generate_locations(state: GameState, db) -> GameState:
    """
    Догенерирует локации при перемещении игрока.

    Args:
        state: GameState (должен быть location_changed, current_location_name)
        db: SQLAlchemy сессия

    Returns:
        GameState с обновлёнными extra-данными
    """
    if not state.location_changed:
        return state

    if not state.current_location_name:
        return state

    logger.info("GenerateLocations: догенерация для '%s'", state.current_location_name)

    # Получаем описание текущей локации и этаж через переданную сессию
    location_desc = ""
    floor_name = ""
    if state.current_location_id:
        from bot.models.location import Location, Floor

        loc = db.get(Location, state.current_location_id)
        if loc:
            location_desc = loc.description or ""
            floor = db.get(Floor, loc.floor_id)
            if floor:
                floor_name = floor.name

    # Проверяем, есть ли уже связи у текущей локации (через переданную сессию)
    if state.current_location_id:
        from bot.models.location import LocationConnection
        from sqlalchemy import select, func

        conn_count = db.execute(
            select(func.count(LocationConnection.from_location_id))
            .where(LocationConnection.from_location_id == state.current_location_id)
        ).scalar() or 0

        if conn_count >= 3:
            logger.info("GenerateLocations: у локации уже %d связей, пропускаем", conn_count)
            return state

    prompt = LOCATION_GEN_PROMPT.format(
        current_location=state.current_location_name,
        current_description=location_desc or "Неизвестно",
        floor_name=floor_name or "Неизвестно",
        cycle=state.current_cycle,
        time=state.current_time,
    )

    try:
        response = _call_llm(prompt)
        data = _extract_json(response)
        if data:
            state = _create_locations_in_db(state, data, db)
        else:
            logger.warning("GenerateLocations: не удалось распарсить ответ")
    except Exception as e:
        logger.warning("GenerateLocations: ошибка: %s", e)

    return state