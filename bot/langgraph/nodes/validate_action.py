# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Validate Action Node
# LLM-based guardrails: проверяет, можно ли совершить действие
# ─────────────────────────────────────────────────

"""
Проверка действия игрока через LLM.

После базовых guardrails (пустота, длина, бан, game_over, инъекции)
запрашивает LLM: "Можно ли это сделать в текущем контексте?"

Это позволяет отсечь:
  - Действия, невозможные в текущей локации
  - Действия, противоречащие логике мира
  - Абсурдные/метагейминговые действия

Использует быструю дешёвую модель (мало токенов).
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

from bot.schemas.game import GameState, ValidationResult
from bot.utils.langfuse_trace import trace_llm_call

logger = logging.getLogger(__name__)


# ── Очистка строк от суррогатов ──────────────────

from bot.utils import clean_str


# ── Конфигурация ─────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

VALIDATE_PROMPT = """Ты — валидатор действий в RPG-игре «Самосбор» (мир Гигахрущёвки).
Проверь, может ли игрок совершить указанное действие в его текущей ситуации.

## Правила мира
- Гигахрущёвка — бесконечное здание без окон, без улицы, без неба, без солнца
- Самосбор — фиолетовый туман и бурая слизь, вызывающие галлюцинации, мутации и смерть
- Выход на улицу, открытие окон, телепортация, полёты — невозможны
- Персонаж не может мгновенно перемещаться между этажами без лестниц/лифтов

## Важно
- Если в описании последней сцены или в инвентаре упоминается предмет — персонаж может его использовать
- Если в описании упоминается NPC, тварь, существо — персонаж может с ними взаимодействовать
- Если персонаж хочет осмотреться/проверить/найти — разрешай, это часть игры
- Предмет считается в инвентаре, если он указан в списке инвентаря
- Разрешено взаимодействовать с предметами, которые описаны в сцене (даже если они не в инвентаре)
- Не блокируй творческие действия, если они не нарушают правила мира
- Блокируй только: нарушение правил мира, использование несуществующих предметов, телепортацию, полёты, читерство

## Последняя сцена (описание мастером)
{last_scene}

## Инвентарь игрока
{inventory}

## Текущая ситуация
Локация: {location}
Цикл: {cycle}, время: {time}
Рядом: {npcs}
Описание: {location_description}

## Действие игрока
{user_input}

## Ответ
Только JSON без пояснений:
```json
{{"allowed": true/false, "reason": "если false — объяснение почему (одно предложение). Если true — пустая строка."}}
```"""


# ── Клиент ───────────────────────────────────────


_retry_decorator = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


@_retry_decorator
def _call_llm(prompt: str) -> str:
    """Быстрый дешёвый LLM-запрос на валидацию."""
    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=256,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM вернул пустой ответ")
    return content.strip()


def _extract_validation(text: str) -> ValidationResult | None:
    """Извлекает ValidationResult из ответа LLM."""
    # Ищем JSON блок
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    json_str = match.group(1).strip() if match else text.strip()

    # Если нет ```json, пробуем распарсить весь текст
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Ищем { }
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            try:
                data = json.loads(brace.group(0))
            except json.JSONDecodeError:
                return None
        else:
            return None

    return ValidationResult(
        allowed=bool(data.get("allowed", True)),
        reason=str(data.get("reason", "")),
    )


# ── Node ──────────────────────────────────────────

def validate_action(state: GameState) -> GameState:
    """
    Проверяет действие игрока через LLM.

    Args:
        state: GameState (должен быть user_input, current_location_name)

    Returns:
        GameState с validation_result или error
    """
    if not state.user_input or not state.user_input.strip():
        # Пустое — guardrails уже отловили, но на всякий случай
        state.validation_result = ValidationResult(allowed=False, reason="Пустое сообщение.")
        return state

    if state.error:
        return state

    logger.info("ValidateAction: проверка '%s' для chat_id=%s",
                state.user_input[:50], state.chat_id)

    # Собираем контекст
    npc_names = []
    for npc in state.extra.get("npcs_in_location", []):
        name = npc.get("name") or f"NPC {npc.get('id', '?')}"
        npc_names.append(name)

    location_desc = ""
    if state.current_location_id:
        location_desc = state.extra.get("location_description", "")

    # Последняя сцена (из истории, последнее сообщение ассистента)
    last_scene = ""
    if state.memory:
        for msg in reversed(state.memory):
            if msg.get("role") == "assistant":
                last_scene = msg.get("content", "")[:500]
                break

    # Инвентарь (из extra, если memory загрузил)
    inventory_items = state.extra.get("player_inventory", [])
    inventory_str = ", ".join(inventory_items) if inventory_items else "пусто"

    prompt = VALIDATE_PROMPT.format(
        last_scene=clean_str(last_scene or "Новая игра, мир только что создан"),
        inventory=clean_str(inventory_str),
        location=clean_str(state.current_location_name or "Неизвестно"),
        cycle=state.current_cycle,
        time=state.current_time,
        npcs=clean_str(", ".join(npc_names) if npc_names else "никого"),
        location_description=clean_str(location_desc or "Неизвестно"),
        user_input=clean_str(state.user_input),
    )

    try:
        response = _call_llm(prompt)
        result = _extract_validation(response)
        if result is None:
            logger.warning("ValidateAction: не удалось распарсить ответ LLM")
            # Если не распарсили — пропускаем (разрешаем)
            state.validation_result = ValidationResult(allowed=True)
        else:
            state.validation_result = result
            if not result.allowed:
                state.error = f"🚫 {result.reason}"
                logger.info("ValidateAction: действие '%s' запрещено: %s",
                            state.user_input[:30], result.reason)
            else:
                logger.info("ValidateAction: действие разрешено")
    except Exception as e:
        logger.warning("ValidateAction: ошибка LLM: %s, пропускаем", e)
        # При ошибке LLM — пропускаем (разрешаем), не блокируем игру
        state.validation_result = ValidationResult(allowed=True)

    return state
