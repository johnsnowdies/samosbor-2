# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Embedder (Ollama / OpenRouter)
# ─────────────────────────────────────────────────

"""
Генератор эмбедингов.

Поддерживает два провайдера:
  - ollama: bge-m3, nomic-embed-text, mxbai-embed-large (локально, бесплатно)
  - openrouter: text-embedding-3-small (облачный, $0.02/1M токенов)

Выбор через EMBEDDING_PROVIDER в .env (по умолч. ollama).
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

from dotenv import load_dotenv
from openai import APIError, OpenAI, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ── Конфигурация ─────────────────────────────────

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").strip().lower()

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "bge-m3")

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "text-embedding-3-small")

# Общие
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "1024"))
MAX_BATCH_SIZE = 128  # макс. строк в одном запросе к API


# ── Клиент ───────────────────────────────────────

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Создаёт/возвращает кешированный OpenAI-клиент."""
    global _client
    if _client is not None:
        return _client

    if EMBEDDING_PROVIDER == "ollama":
        logger.info("Эмбединг через Ollama: %s", OLLAMA_MODEL)
        _client = OpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",  # заглушка, Ollama не требует ключа
        )

    elif EMBEDDING_PROVIDER == "openrouter":
        if not OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY не задан. "
                "Укажите его в .env или переключите EMBEDDING_PROVIDER=ollama"
            )
        logger.info("Эмбединг через OpenRouter: %s", OPENROUTER_MODEL)
        _client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )

    else:
        raise ValueError(
            f"Неизвестный EMBEDDING_PROVIDER={EMBEDDING_PROVIDER!r}. "
            "Используйте 'ollama' или 'openrouter'"
        )

    return _client


def _get_model() -> str:
    """Возвращает название модели для текущего провайдера."""
    if EMBEDDING_PROVIDER == "ollama":
        return OLLAMA_MODEL
    return OPENROUTER_MODEL


# ── Retry policy ─────────────────────────────────

_retry_decorator = retry(
    retry=retry_if_exception_type((APIError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ── Embed ─────────────────────────────────────────

@_retry_decorator
def embed_text(text: str) -> list[float]:
    """
    Генерирует эмбединг для одного текста.

    Args:
        text: Входной текст (чанк)

    Returns:
        Вектор размерности EMBEDDING_DIMS
    """
    client = _get_client()
    model = _get_model()
    kwargs = {"model": model, "input": text}

    # OpenRouter support dimensions param, Ollama ignores it
    if EMBEDDING_PROVIDER == "openrouter":
        kwargs["dimensions"] = EMBEDDING_DIMS

    response = client.embeddings.create(**kwargs)
    return response.data[0].embedding


@_retry_decorator
def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """
    Генерирует эмбединги для нескольких текстов (батч).

    Args:
        texts: Список текстов

    Returns:
        Список векторов размерности EMBEDDING_DIMS
    """
    client = _get_client()
    model = _get_model()
    kwargs = {"model": model, "input": list(texts)}

    if EMBEDDING_PROVIDER == "openrouter":
        kwargs["dimensions"] = EMBEDDING_DIMS

    response = client.embeddings.create(**kwargs)
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


def embed_many(
    texts: Sequence[str],
    batch_size: int = MAX_BATCH_SIZE,
) -> list[list[float]]:
    """
    Генерирует эмбединги для большого списка текстов
    с разбивкой на батчи и retry.

    Args:
        texts: Список текстов
        batch_size: Размер одного батча

    Returns:
        Список векторов
    """
    results: list[list[float]] = []
    total = len(texts)
    for start in range(0, total, batch_size):
        batch = texts[start:start + batch_size]
        logger.info("Эмбединг батча %d–%d из %d", start, start + len(batch), total)
        embeddings = embed_batch(batch)
        results.extend(embeddings)
    return results


# ── Self-test ─────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    test_texts = [
        "В начале был Самосбор. Пурпурный туман окутал бесконечные этажи.",
    ]
    logger.info("Тест эмбединга %d текстов через %s…",
                len(test_texts), EMBEDDING_PROVIDER)
    vectors = embed_many(test_texts)
    for i, vec in enumerate(vectors):
        logger.info("Текст %d: размерность %d, первые 5 значений: %s",
                    i, len(vec), vec[:5])