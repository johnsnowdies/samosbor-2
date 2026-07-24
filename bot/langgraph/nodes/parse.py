# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Parse Node
# ─────────────────────────────────────────────────

"""
Парсинг ответа LLM в структурированную модель GameAction.

Обрабатывает:
  - JSON внутри ```json ... ``` блоков
  - JSON без обёртки
  - trailing text после JSON
  - невалидный JSON с сообщением об ошибке для ретрая
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from bot.schemas.game import GameAction, GameState

logger = logging.getLogger(__name__)


# ── Извлечение JSON из ответа LLM ─────────────────

def _extract_json(text: str) -> str | None:
    """
    Извлекает JSON из ответа LLM.

    Сначала ищет ```json ... ``` блок.
    Если не нашёл — пробует распарсить весь текст как JSON.
    Если и это не вышло — ищет первый { ... } в тексте.

    Args:
        text: Сырой ответ LLM

    Returns:
        Строка с JSON или None
    """
    if not text or not text.strip():
        return None

    # 1. ```json ... ``` блок
    match = re.search(
        r'```(?:json)?\s*\n?(.*?)\n?```',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        candidate = match.group(1).strip()
        # Пробуем распарсить
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass  # Кусок между ``` невалидный — пробуем другие варианты

    # 2. Весь текст как JSON
    text_stripped = text.strip()
    try:
        json.loads(text_stripped)
        return text_stripped
    except json.JSONDecodeError:
        pass

    # 3. Первый { ... } в тексте (игнорируем мусор до и после)
    brace_match = re.search(r'\{.*\}', text_stripped, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return None


def _normalize_json(data: dict[str, Any]) -> dict[str, Any]:
    """
    Нормализует поля JSON перед валидацией Pydantic.

    - Приводит game_over к bool
    - Приводит пустые списки к None
    - npc_actions: строки → объекты NPCAction (npc_id=0)
    """
    # game_over может быть строкой "false"/"true"
    if "game_over" in data and isinstance(data["game_over"], str):
        data["game_over"] = data["game_over"].lower() in ("true", "yes", "да")

    # npc_actions может быть массивом строк вместо объектов
    if "npc_actions" in data and isinstance(data["npc_actions"], list):
        normalized = []
        for item in data["npc_actions"]:
            if isinstance(item, str):
                # Строка → NPCAction без npc_id
                normalized.append({"npc_id": 0, "action": item})
            elif isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"npc_id": 0, "action": str(item)})
        data["npc_actions"] = normalized

    return data


# ── Parse ──────────────────────────────────────────

def parse_response(state: GameState) -> GameState:
    """
    Парсит ответ LLM в структурированную модель.

    Args:
        state: GameState с llm_response

    Returns:
        GameState с parsed_response или error
    """
    if not state.llm_response:
        state.error = "Нет ответа от LLM для парсинга."
        logger.warning("Parse: пустой llm_response для chat_id=%s", state.chat_id)
        return state

    logger.info("Parse: парсинг ответа (%d символов) для chat_id=%s",
                len(state.llm_response), state.chat_id)

    # 1. Извлечение JSON
    json_str = _extract_json(state.llm_response)
    if json_str is None:
        state.error = (
            "Не удалось извлечь JSON из ответа LLM. "
            "Пожалуйста, перегенерируй ответ в правильном JSON-формате."
        )
        logger.warning("Parse: JSON не найден в ответе LLM для chat_id=%s",
                       state.chat_id)
        return state

    # 2. Парсинг в словарь
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        state.error = f"Ошибка парсинга JSON: {e}"
        logger.warning("Parse: невалидный JSON для chat_id=%s: %s",
                       state.chat_id, str(e))
        return state

    # 3. Нормализация
    data = _normalize_json(data)

    # 4. Валидация Pydantic
    try:
        action = GameAction(**data)
        state.parsed_response = action
        logger.info("Parse: успешно распарсен ответ для chat_id=%s", state.chat_id)
    except ValidationError as e:
        state.error = (
            f"Ответ LLM не соответствует формату. Ошибки:\n"
            f"{_format_validation_errors(e)}"
        )
        logger.warning("Parse: ошибка валидации для chat_id=%s: %s",
                       state.chat_id, str(e))

    return state


def _format_validation_errors(error: ValidationError) -> str:
    """Форматирует ошибки Pydantic в человекочитаемый вид."""
    lines = []
    for err in error.errors():
        field = " → ".join(str(loc) for loc in err["loc"])
        msg = err["msg"]
        lines.append(f"  - {field}: {msg}")
    return "\n".join(lines)