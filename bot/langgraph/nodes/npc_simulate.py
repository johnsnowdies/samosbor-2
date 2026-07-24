# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — NPC Simulate Node
# ─────────────────────────────────────────────────

"""
Симуляция NPC после хода игрока.

Запускает FSM для каждого NPC в той же локации.
Без LLM — только правила.

Если в ответе LLM (parsed_response) есть npc_actions — применяем их.
"""

from __future__ import annotations

import logging
import random

from bot.schemas.game import GameState

logger = logging.getLogger(__name__)


# ── NPC Simulate ──────────────────────────────────

def simulate_npcs(state: GameState) -> GameState:
    """
    Симулирует поведение NPC после хода игрока.

    Args:
        state: Текущее состояние

    Returns:
        GameState с обновлёнными NPC событиями в extra
    """
    npcs = state.extra.get("npcs_in_location", [])
    if not npcs:
        logger.debug("NPC: нет NPC в локации, пропускаем")
        return state

    logger.info("NPC: симуляция %d NPC в локации", len(npcs))

    events = []

    # 1. Если LLM вернула npc_actions — применяем их
    if state.parsed_response and state.parsed_response.npc_actions:
        for npc_action in state.parsed_response.npc_actions:
            events.append({
                "npc_id": npc_action.npc_id,
                "action": npc_action.action,
                "source": "llm",
            })
            logger.debug("NPC: действие от LLM — NPC %s: %s",
                         npc_action.npc_id, npc_action.action)

    # 2. FSM для остальных NPC (кто не упомянут в LLM-ответе)
    mentioned_npc_ids = {
        a.npc_id
        for a in (state.parsed_response.npc_actions if state.parsed_response else [])
    }

    for npc in npcs:
        npc_id = npc.get("id")
        if npc_id in mentioned_npc_ids:
            continue  # уже обработан LLM

        action = _npc_fsm_step(npc)
        if action:
            events.append({
                "npc_id": npc_id,
                "npc_name": npc.get("name", f"NPC {npc_id}"),
                "action": action,
                "source": "fsm",
            })

    state.extra["npc_events"] = events

    if events:
        logger.info("NPC: %d событий сгенерировано", len(events))
    else:
        logger.debug("NPC: нет событий")

    return state


def _npc_fsm_step(npc: dict) -> str | None:
    """
    Один шаг FSM для NPC.

    Args:
        npc: Данные NPC из extra

    Returns:
        Описание действия или None (если NPC бездействует)
    """
    danger_level = npc.get("danger_level", 0.0)
    faction = npc.get("faction", "")

    # 30% шанс что NPC что-то делает
    if random.random() > 0.3:
        return None

    # Поведение в зависимости от фракции и уровня опасности
    if danger_level > 0.7:
        return random.choice([
            "настороженно оглядывается",
            "сжимает оружие",
            "шипит на вас",
        ])
    elif danger_level > 0.3:
        return random.choice([
            "проходит мимо, не обращая внимания",
            "кашляет в углу",
            "что-то бормочет себе под нос",
        ])
    else:
        return random.choice([
            "мирно дремлет",
            "перебирает свои вещи",
            "безучастно смотрит в стену",
        ])