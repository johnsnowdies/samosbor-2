# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Fact Check Node
# Проверка ответа LLM на фактологическую корректность
# ─────────────────────────────────────────────────

"""
Проверяет ответ LLM после парсинга и сохранения.

Проверяет:
  - Предметы из `items` существуют в инвентаре или локации
  - NPC из `npc_actions` находятся в текущей локации
  - Локация из `location` достижима (есть связь из текущей)
  - Квесты не дублируют существующие

При серьёзных несоответствиях — исправляет ответ (убирает несуществующие предметы/NPC).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.models.item import Item
from bot.models.location import Location, LocationConnection
from bot.models.npc import NPC
from bot.models.person import Person
from bot.models.task import Task
from bot.schemas.game import GameState, FactCheckResult

logger = logging.getLogger(__name__)


def _check_items(state: GameState, db: Session) -> list[str]:
    """Проверяет, что предметы из items есть в инвентаре."""
    issues = []
    if not state.parsed_response or not state.parsed_response.items:
        return issues
    if not state.player_id:
        return issues

    for item_name in state.parsed_response.items:
        existing = db.execute(
            select(Item).where(
                Item.session_id == state.session_id,
                Item.name == item_name,
                (
                    (Item.owner_id == state.player_id) |
                    (Item.location_id == state.current_location_id)
                ),
            )
        ).first()
        if not existing:
            issues.append(f"Предмет '{item_name}' не найден у игрока или в локации")
    return issues


def _check_npcs(state: GameState, db: Session) -> list[str]:
    """Проверяет, что NPC из npc_actions есть в текущей локации."""
    issues = []
    if not state.parsed_response or not state.parsed_response.npc_actions:
        return issues
    if not state.current_location_id:
        return issues

    for npc_action in state.parsed_response.npc_actions:
        npc_id = npc_action.npc_id
        existing = db.execute(
            select(NPC).join(Person, NPC.person_id == Person.id).where(
                NPC.person_id == npc_id,
                Person.current_location_id == state.current_location_id,
                Person.session_id == state.session_id,
            )
        ).first()
        if not existing:
            npc_anywhere = db.get(NPC, npc_id)
            if npc_anywhere:
                issues.append(f"NPC #{npc_id} не в текущей локации")
            else:
                issues.append(f"NPC #{npc_id} не существует в этой сессии")
    return issues


def _check_location(state: GameState, db: Session) -> list[str]:
    """Проверяет, что новая локация существует и достижима."""
    issues = []
    if not state.parsed_response or not state.parsed_response.location:
        return issues
    if not state.current_location_id:
        return issues

    new_loc_name = state.parsed_response.location
    if new_loc_name == state.current_location_name:
        return issues

    new_loc = db.execute(
        select(Location).where(
            Location.session_id == state.session_id,
            Location.name == new_loc_name,
        )
    ).scalar_one_or_none()

    if not new_loc:
        logger.info("FactCheck: новая локация '%s' будет создана generate_locations", new_loc_name)
        return issues

    connection = db.execute(
        select(LocationConnection).where(
            LocationConnection.from_location_id == state.current_location_id,
            LocationConnection.to_location_id == new_loc.id,
        )
    ).first()

    if not connection:
        issues.append(f"Нет прямого пути из '{state.current_location_name}' в '{new_loc_name}'")
    return issues


def _check_quests(state: GameState, db: Session) -> list[str]:
    """Проверяет, что квесты не дублируют существующие."""
    issues = []
    if not state.parsed_response or not state.parsed_response.quests:
        return issues

    for quest_desc in state.parsed_response.quests:
        existing = db.execute(
            select(Task).where(
                Task.session_id == state.session_id,
                Task.title == quest_desc[:128],
            )
        ).first()
        if existing:
            issues.append(f"Квест '{quest_desc[:50]}...' уже существует")
    return issues


# ── Node ──────────────────────────────────────────

def fact_check(state: GameState, db: Session) -> GameState:
    """
    Проверяет ответ LLM на фактологическую корректность.

    Args:
        state: GameState с parsed_response
        db: SQLAlchemy сессия

    Returns:
        GameState с факт-чек результатом
    """
    if not state.parsed_response:
        logger.debug("FactCheck: нет parsed_response, пропускаем")
        return state

    logger.info("FactCheck: проверка ответа для chat_id=%s", state.chat_id)

    all_issues: list[str] = []
    all_issues.extend(_check_items(state, db))
    all_issues.extend(_check_npcs(state, db))
    all_issues.extend(_check_location(state, db))
    all_issues.extend(_check_quests(state, db))

    if all_issues:
        logger.info("FactCheck: найдено %d проблем: %s", len(all_issues), all_issues[:3])
        state.fact_check = FactCheckResult(is_coherent=False, issues=all_issues)

        action = state.parsed_response
        if action and any("не в текущей локации" in iss or "не существует" in iss for iss in all_issues):
            bad_npc_ids = set()
            for iss in all_issues:
                if "NPC #" in iss:
                    try:
                        npc_id = int(iss.split("#")[1].split()[0])
                        bad_npc_ids.add(npc_id)
                    except (IndexError, ValueError):
                        pass
            action.npc_actions = [
                na for na in action.npc_actions
                if na.npc_id not in bad_npc_ids
            ]
            logger.info("FactCheck: ответ скорректирован (удалены NPC %s)", bad_npc_ids)
    else:
        state.fact_check = FactCheckResult(is_coherent=True)
        logger.debug("FactCheck: всё корректно")

    return state