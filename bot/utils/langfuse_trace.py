# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Langfuse трейсинг
# ─────────────────────────────────────────────────

"""
Langfuse integration для LangGraph.

Предоставляет:
  1. get_langfuse_handler() — CallbackHandler для LangGraph/LangChain
  2. trace_llm_call() — контекстный менеджер для ручного трейсинга
     прямых вызовов OpenAI/OpenRouter (которые не проходят через LangChain)

Использование в LangGraph (activities.py):
    handler = get_langfuse_handler()
    if handler:
        result = graph.invoke(state, {"callbacks": [handler]})
    else:
        result = graph.invoke(state)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

# ── Конфигурация ─────────────────────────────────

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL", "http://langfuse:3000")

# ── CallbackHandler для LangGraph (ленивый синглтон) ──

_handler_instance = None


def get_langfuse_handler():
    """
    Возвращает Langfuse CallbackHandler для LangGraph/LangChain.

    Инициализируется один раз (лениво) при первом вызове.
    Возвращает None, если Langfuse не настроен.

    CallbackHandler автоматически трейсит:
      - Структуру графа: каждую ноду как отдельный span
      - LangChain компоненты внутри нод (если используются)
    """
    global _handler_instance

    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return None

    if _handler_instance is not None:
        return _handler_instance

    try:
        # Устанавливаем env vars для CallbackHandler (читает их автоматически)
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", LANGFUSE_PUBLIC_KEY)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", LANGFUSE_SECRET_KEY)
        os.environ.setdefault("LANGFUSE_BASE_URL", LANGFUSE_BASE_URL)

        from langfuse.langchain import CallbackHandler

        _handler_instance = CallbackHandler()
        logger.info("Langfuse: CallbackHandler инициализирован (%s)", LANGFUSE_BASE_URL)
    except Exception as e:
        logger.warning("Langfuse: ошибка инициализации CallbackHandler: %s", e)
        _handler_instance = None

    return _handler_instance


# ── Langfuse клиент (для ручного трейсинга) ──────

_langfuse = None


def _get_langfuse():
    """Возвращает Langfuse SDK клиент (ленивая инициализация)."""
    global _langfuse
    if _langfuse is None and LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
        try:
            from langfuse import Langfuse
            _langfuse = Langfuse(
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_BASE_URL,
            )
        except Exception as e:
            logger.warning("Langfuse: ошибка инициализации SDK: %s", e)
            _langfuse = None
    return _langfuse


# ── Контекстный менеджер для ручного трейсинга LLM ──

class _TraceContext:
    """Хранит ссылки на trace и generation для одного LLM вызова."""

    def __init__(self):
        self.trace = None
        self.generation = None

    def set_output(self, output: str, usage: dict | None = None):
        """Завершает generation с результатом."""
        if self.generation:
            self.generation.end(output=output, usage=usage)

    def set_error(self, error: str):
        """Завершает generation с ошибкой."""
        if self.generation:
            self.generation.end(output=None, usage=None, level="ERROR", status_message=error)


@contextmanager
def trace_llm_call(
    chat_id: int,
    cycle: int = 1,
    location: str | None = None,
    model: str = "deepseek/deepseek-v4-flash",
    input_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Generator[_TraceContext, Any, None]:
    """
    Контекстный менеджер для ручного трейсинга LLM вызовов.

    Нужен потому что CallbackHandler не видит прямые вызовы
    openai.OpenAI() — только LangChain компоненты.

    Args:
        chat_id: ID чата
        cycle: Текущий цикл игры
        location: Название локации
        model: Название модели
        input_prompt: Входной промпт
        temperature: Температура
        max_tokens: Максимум токенов

    Yields:
        _TraceContext с методами set_output() и set_error()
    """
    lf = _get_langfuse()
    ctx = _TraceContext()

    if lf:
        try:
            trace_name = f"game_{chat_id}_{cycle}"
            ctx.trace = lf.trace(
                name=trace_name,
                metadata={
                    "chat_id": chat_id,
                    "cycle": cycle,
                    "location": location,
                    "model": model,
                },
            )
            ctx.generation = ctx.trace.generation(
                name="llm_call",
                model=model,
                model_parameters={
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                input=input_prompt,
            )
        except Exception as e:
            logger.warning("Langfuse: ошибка создания trace: %s", e)
            ctx.trace = None
            ctx.generation = None

    try:
        yield ctx
    except Exception as e:
        ctx.set_error(str(e))
        raise