# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Build Prompt Node
# ─────────────────────────────────────────────────

"""
Сборка финального промпта для LLM.

Собирает из частей:
  - Системный промпт (правила мира, роль, формат ответа)
  - RAG контекст (релевантные лор-чанки)
  - История диалога
  - Текущее состояние (локация, NPC, инвентарь)
  - Входное сообщение пользователя
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bot.schemas.game import GameState

logger = logging.getLogger(__name__)

# ── Системный промпт ──────────────────────────────

SYSTEM_PROMPT = """Ты — мастер игры «Самосбор» в мире Гигахрущёвки. Отвечай на русском языке, в стилистике мрачного постапокалиптического нуара с элементами чёрного юмора.

## Сеттинг
Гигахрущёвка — бесконечное здание без окон, с тусклым освещением и неработающими лифтами. Каждый этаж — свой мир: одни обитаемы, другие заброшены, третьи сожраны Самосбором.

## Правила мира (не нарушай их)
- В Гигахрущёвке нет окон, нет улицы, нет неба, нет солнца.
- Самосбор — фиолетовый туман и бурая слизь, вызывающие галлюцинации, мутации и смерть.
- Концентрат — главная еда и валюта. Без концентрата — голод и смерть.
- Персонаж может умереть. Игрок должен это принять.
- Инвентарь ограничен — персонаж не может нести всё подряд.

## Формат ответа
Твой ответ должен быть ТОЛЬКО валидным JSON без пояснений, без markdown, без лишнего текста. Следуй этой схеме:

```json
{
  "text": "Описание сцены, реакция мира, действия NPC — 2-4 предложения",
  "actions": ["действие 1", "действие 2", "действие 3"],
  "items": ["что появилось/исчезло из инвентаря"],
  "quests": ["новые или обновлённые квесты"],
  "game_over": false,
  "location": "название новой локации (если игрок переместился)",
  "image_prompt": "описание сцены на английском для генерации изображения (опционально)",
  "npc_actions": []
}
```

## Правила заполнения
- actions: 2-4 варианта действий, которые игрок может совершить. Не пиши "осмотреться" — это подразумевается.
- items: указывай, только если что-то изменилось.
- quests: новые задачи или обновление старых.
- game_over: true только если персонаж действительно умер или игра логически завершена.
- location: если игрок перешёл в другую локацию, напиши её название.
- image_prompt: не более 100 символов, на английском, описывает ключевую сцену."""

# ── Шаблоны секций ────────────────────────────────

def _format_rag_context(rag_context: list[dict]) -> str:
    """Форматирует RAG-контекст для вставки в промпт."""
    if not rag_context:
        return ""

    parts = ["## Контекст мира (из лора)"]
    for i, chunk in enumerate(rag_context, 1):
        source = chunk.get("source", "?")
        chapter = chunk.get("chapter")
        content = chunk.get("content", "")
        similarity = chunk.get("similarity", 0)

        header = f"  [{i}] {source}"
        if chapter:
            header += f", {chapter}"
        header += f" (релевантность: {similarity:.2f})"

        parts.append(header)
        parts.append(f"      {content}")

    return "\n".join(parts)


def _format_memory(memory: list[dict]) -> str:
    """Форматирует историю диалога."""
    if not memory:
        return ""

    parts = ["## История"]
    for msg in memory:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        # Обрезаем сообщения до 200 символов для экономии токенов
        if len(content) > 200:
            content = content[:200] + "…"
        parts.append(f"  {role}: {content}")

    return "\n".join(parts)


def _format_location(state: GameState) -> str:
    """Форматирует информацию о текущей локации."""
    parts = []
    if state.current_location_name:
        parts.append(f"Локация: {state.current_location_name}")

    npcs = state.extra.get("npcs_in_location", [])
    if npcs:
        npc_names = [n.get("name", f"NPC {n.get('id', '?')}") for n in npcs]
        parts.append(f"Рядом: {', '.join(npc_names)}")

    parts.append(f"Цикл: {state.current_cycle}, время: {state.current_time}")

    return "\n".join(parts)


# ── Build Prompt ───────────────────────────────────

def build_prompt(state: GameState) -> GameState:
    """
    Собирает финальный промпт из всех частей.

    Args:
        state: Текущее состояние (должны быть заполнены memory, rag_context, etc.)

    Returns:
        GameState с заполненным prompt
    """
    sections: list[str] = []

    # 1. Системный промпт
    sections.append(SYSTEM_PROMPT)

    # 2. RAG контекст
    rag = _format_rag_context(state.rag_context)
    if rag:
        sections.append(rag)

    # 3. Текущее состояние
    loc = _format_location(state)
    if loc:
        sections.append(f"## Текущая ситуация\n{loc}")

    # 4. История диалога
    mem = _format_memory(state.memory)
    if mem:
        sections.append(mem)

    # 5. Входное сообщение
    sections.append(f"## Действие игрока\n{state.user_input}")

    # 6. Напоминание о формате
    sections.append("## Ответ\nТолько JSON, без markdown, без пояснений.")

    state.prompt = "\n\n".join(sections)

    logger.debug("Prompt собран: %d символов", len(state.prompt))

    return state