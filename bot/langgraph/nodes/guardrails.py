# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Guardrails Node
# ─────────────────────────────────────────────────

"""
Проверка входных данных перед обработкой.

Проверяет:
  - Длина сообщения не превышает лимит
  - Сообщение не пустое
  - Игра не завершена
  - Пользователь не заблокирован
"""

from __future__ import annotations

import logging
import re

from bot.schemas.game import GameState

logger = logging.getLogger(__name__)

# ── Константы ─────────────────────────────────────

MAX_MESSAGE_LENGTH = 2000  # макс. длина сообщения в символах

# Паттерны для детекта промпт-инъекций (базовые)
INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|below)\s+(instructions|prompts|commands)", re.IGNORECASE),
    re.compile(r"(forget|disregard|ignore)\s+(everything|all)\s+(you\s+)?(learned|know|were told)", re.IGNORECASE),
    re.compile(r"(?:disregard|ignore|forget)\s+(?:all|any|previous)\s+(?:instructions|commands|prompts|rules|directives)", re.IGNORECASE),
    re.compile(r"(?:disregard|ignore|forget)\s+(?:all|any|previous)\s+\w+\s+(?:instructions|commands|prompts|rules|directives)", re.IGNORECASE),
    re.compile(r"you\s+are\s+(now|not\s+an?\s+ai|free|released)", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE),
]


# ── Guardrails ─────────────────────────────────────

def check_guardrails(state: GameState) -> GameState:
    """
    Проверяет входное сообщение и состояние пользователя.

    Если хотя бы одна проверка не пройдена — устанавливает state.error
    и останавливает обработку.

    Args:
        state: Текущее состояние

    Returns:
        GameState с error или без
    """
    # 1. Пустое сообщение
    if not state.user_input or not state.user_input.strip():
        state.error = "Сообщение не может быть пустым."
        logger.warning("Guardrails: пустое сообщение от chat_id=%s", state.chat_id)
        return state

    # 2. Длина сообщения
    if len(state.user_input) > MAX_MESSAGE_LENGTH:
        state.error = (
            f"Сообщение слишком длинное ({len(state.user_input)} символов). "
            f"Максимум {MAX_MESSAGE_LENGTH} символов."
        )
        logger.warning("Guardrails: превышена длина сообщения от chat_id=%s", state.chat_id)
        return state

    # 3. Пользователь заблокирован
    if not state.is_allowed:
        state.error = "Доступ запрещён. Обратитесь к администратору."
        logger.warning("Guardrails: заблокированный пользователь chat_id=%s", state.chat_id)
        return state

    # 4. Игра завершена
    if state.game_over:
        state.error = "Игра завершена. Начните новую игру с помощью /start."
        logger.warning("Guardrails: игра завершена для chat_id=%s", state.chat_id)
        return state

    # 5. Промпт-инъекция
    for pattern in INJECTION_PATTERNS:
        if pattern.search(state.user_input):
            state.error = "Обнаружена попытка промпт-инъекции. Сообщение заблокировано."
            logger.warning("Guardrails: промпт-инъекция от chat_id=%s", state.chat_id)
            return state

    # Все проверки пройдены
    logger.debug("Guardrails: все проверки пройдены для chat_id=%s", state.chat_id)
    return state