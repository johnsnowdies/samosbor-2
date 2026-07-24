# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — LLM Call Node
# ─────────────────────────────────────────────────

"""
Вызов LLM (DeepSeek V4 Flash через OpenRouter).

Принимает собранный промпт из build_prompt,
отправляет в OpenRouter, сохраняет ответ в state.llm_response.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
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

load_dotenv()

logger = logging.getLogger(__name__)

# ── Конфигурация ─────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")

# Параметры генерации
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))



# ── Retry ─────────────────────────────────────────

_retry_decorator = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ── Call LLM ──────────────────────────────────────

@_retry_decorator
def _call_llm(prompt: str) -> str:
    """
    Отправляет запрос в OpenRouter и возвращает текст ответа.

    Args:
        prompt: Полный промпт для LLM

    Returns:
        Текст ответа LLM

    Raises:
        ValueError: если ответ пустой
    """
    from bot.utils import clean_str
    prompt = clean_str(prompt)

    client = get_openai_client()

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM вернул пустой ответ")

    logger.info(
        "LLM ответ получен: %d токенов (input=%d, output=%d)",
        response.usage.total_tokens if response.usage else 0,
        response.usage.prompt_tokens if response.usage else 0,
        response.usage.completion_tokens if response.usage else 0,
    )

    return content.strip()


# ── Node ──────────────────────────────────────────

def call_llm(state: GameState) -> GameState:
    """
    Отправляет промпт в LLM и сохраняет ответ.

    Args:
        state: GameState с заполненным prompt

    Returns:
        GameState с llm_response или error
    """
    if not state.prompt:
        state.error = "Промпт пустой — нечего отправлять в LLM."
        logger.warning("LLM: пустой промпт для chat_id=%s", state.chat_id)
        return state

    logger.info(
        "LLM: запрос для chat_id=%s (%d символов промпта)",
        state.chat_id, len(state.prompt),
    )

    try:
        response = _call_llm(state.prompt)
        state.llm_response = response
        logger.debug("LLM: ответ получен (%d символов)", len(response))
    except Exception as e:
        state.error = f"Ошибка при вызове LLM: {str(e)}"
        logger.error("LLM: ошибка для chat_id=%s: %s", state.chat_id, str(e))

    return state