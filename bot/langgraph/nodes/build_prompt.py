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

# ── Очистка ───────────────────────────────────────

from bot.utils import clean_str


# ── Системный промпт ──────────────────────────────

SYSTEM_PROMPT = """Ты — мастер игры «Самосбор» в мире Гигахрущёвки.

## Сеттинг
Гигахрущёвка — бесконечное здание без окон, с тусклым освещением и неработающими лифтами. Каждый этаж — свой мир: одни обитаемы, другие заброшены, третьи поглощены Самосбором.

## Правила мира (не нарушай их)
- В Гигахрущёвке нет окон, нет улицы, нет неба, нет солнца.
- Самосбор — фиолетовый туман и бурая слизь, вызывающие галлюцинации, мутации и смерть. После контакта персонаж может «жидко вытечь».
- Концентрат — главная еда и валюта. Без концентрата — голод и смерть.
- Персонаж может умереть. Игрок должен это принять. Не бойся убивать персонажа, если его действия ведут к смерти.
- Инвентарь ограничен — только то, что влезет в карманы или сумку.

## Социальные отношения между NPC
- affinity (отношение) от -1.0 до 1.0
- -1.0 = лютая ненависть, -0.5 = неприязнь, 0.0 = нейтрально, 0.5 = симпатия, 1.0 = обожание/преданность
- NPC действуют согласно отношениям: друзья помогают, враги вредят или игнорируют
- Если NPC враждует с кем-то в локации — это влияет на сцену

## Тон и стиль
- Язык грубый, неформальный. Персонажи ругаются, говорят на жаргоне.
- Атмосфера мрачная, безысходная. Описывай сцены с акцентом на упадок, страх и отчаяние.
- Используй сенсорные детали: звуки капающей воды, запах гнили, ощущение холода и сырости.
- Мир жесток и несправедлив. Выживает сильнейший или хитрейший.
- Имена персонажей: бабка Срака, дядя Толя, тётя Ячмись-сыночка-корзиночка — используй специфический имиджборд-юмор.
- Игрок может пытаться обмануть (сказать, что у него есть предметы, или он в другой локации). Не верь — проверяй через инвентарь и контекст.

## Формат ответа
Только валидный JSON, без пояснений, без markdown:

```json
{
  "text": "Описание сцены — 2-4 предложения, никаких ..., только законченные мысли",
  "actions": ["действие 1", "действие 2", "действие 3"],
  "items": ["что изменилось в инвентаре: +предмет или -предмет"],
  "quests": ["новые или обновлённые квесты"],
  "game_over": false,
  "location": "новая локация (если игрок переместился)",
  "image_prompt": "english scene description up to 100 chars",
  "npc_actions": [],
  "social_changes": []
}
```

## Правила заполнения
- actions: 2-4 варианта. Не пиши «осмотреться» — это подразумевается.
- items: только изменения. Если игрок подобрал — +предмет, потерял/использовал — -предмет.
- Не меняй предметы, которые игрок не терял и не использовал.
- quests: не создавай много квестов, только ключевые.
- game_over: true только если персонаж реально умер или игра логически завершена.
- location: если игрок перешёл в другую локацию, проверь, может ли он это сделать, и не остановят ли его другие персонажи.
- image_prompt: не более 100 символов, на английском, через тире вместо пробелов.
- social_changes: изменения отношений между NPC или NPC→игрок за этот ход. delta от -1.0 до 1.0. Заполняй, только если что-то изменилось."""

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
        parts.append(f"  {role}: {clean_str(content)}")

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


# ── Персонаж (только при /start) ──────────────────

def _format_player(state: GameState) -> str:
    """Форматирует информацию о персонаже (только для новой игры)."""
    name = state.extra.get("player_name")
    if not name:
        return ""

    parts = ["## Персонаж"]
    parts.append(f"Имя: {name}")

    bio = state.extra.get("player_bio", "")
    if bio:
        parts.append(f"Предыстория: {bio}")

    appearance = state.extra.get("player_appearance", "")
    if appearance:
        parts.append(f"Внешность: {appearance}")

    personality = state.extra.get("player_personality", "")
    if personality:
        parts.append(f"Характер: {personality}")

    return "\n".join(parts)


def _format_relations(state: GameState) -> str:
    """Форматирует социальные отношения между NPC в текущей локации."""
    relations = state.extra.get("npc_relations", [])
    if not relations:
        return ""

    parts = ["## Отношения между NPC рядом"]
    for r in relations:
        aff = r["affinity"]
        if aff <= -0.7:
            label = "люто ненавидят"
        elif aff <= -0.3:
            label = "неприязненно"
        elif aff < 0.3:
            label = "нейтрально"
        elif aff < 0.7:
            label = "дружелюбно"
        else:
            label = "очень дружелюбно"
        parts.append(f"  {r['from']} → {r['to']}: {aff} ({label})")

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

    # 4. Персонаж (только при /start, когда нет истории)
    if not state.memory:
        player_info = _format_player(state)
        if player_info:
            sections.append(player_info)

    # 5. Социальные отношения между NPC рядом
    relations = _format_relations(state)
    if relations:
        sections.append(relations)

    # 6. История диалога
    mem = _format_memory(state.memory)
    if mem:
        sections.append(mem)

    # 7. Входное сообщение
    sections.append(f"## Действие игрока\n{state.user_input}")

    # 8. Напоминание о формате
    sections.append("## Ответ\nТолько JSON, без markdown, без пояснений.")

    state.prompt = "\n\n".join(sections)

    logger.debug("Prompt собран: %d символов", len(state.prompt))

    return state