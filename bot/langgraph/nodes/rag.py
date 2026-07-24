# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — RAG Retrieve Node
# ─────────────────────────────────────────────────

"""
Поиск релевантных лор-чанков по запросу пользователя.

1. Эмбедит запрос пользователя (Ollama bge-m3)
2. Ищет топ-K похожих чанков в pgvector (cosine similarity)
3. Добавляет результат в state.rag_context
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from bot.rag.embedder import embed_text
from bot.schemas.game import GameState

logger = logging.getLogger(__name__)

# ── Константы ─────────────────────────────────────

TOP_K = 5  # сколько чанков возвращать
MAX_CHUNK_LENGTH = 500  # обрезаем текст чанка до N символов (экономия токенов)


# ── RAG ───────────────────────────────────────────

def retrieve_rag(state: GameState, db: Session) -> GameState:
    """
    Ищет релевантные лор-чанки по запросу пользователя.

    Args:
        state: Текущее состояние (user_input должен быть заполнен)
        db: Сессия SQLAlchemy

    Returns:
        GameState с rag_context
    """
    if not state.user_input or not state.user_input.strip():
        logger.debug("RAG: пустой запрос, пропускаем")
        state.rag_context = []
        return state

    logger.info("RAG: поиск по запросу '%s'", state.user_input[:100])

    try:
        from bot.utils import clean_str
        # 1. Эмбединг запроса через Ollama
        query_embedding = embed_text(clean_str(state.user_input))

        # 2. Поиск в pgvector по cosine similarity
        emb_str = json.dumps(query_embedding)
        rows = db.execute(
            sa_text(f"""
                SELECT source, chunk_index, content,
                       1 - (embedding <=> '{emb_str}'::vector) AS similarity,
                       extra_meta
                FROM document_chunks
                ORDER BY similarity DESC
                LIMIT :top_k
            """),
            {"top_k": TOP_K},
        ).fetchall()

        # 3. Форматирование результата
        chunks: list[dict[str, Any]] = []
        for row in rows:
            content = row.content[:MAX_CHUNK_LENGTH] if row.content else ""
            chapter = None
            if row.extra_meta and isinstance(row.extra_meta, dict):
                chapter = row.extra_meta.get("chapter")

            chunks.append({
                "source": row.source,
                "chunk_index": row.chunk_index,
                "content": content,
                "similarity": round(float(row.similarity), 4),
                "chapter": chapter,
            })

        state.rag_context = chunks
        logger.info("RAG: найдено %d чанков для '%s'", len(chunks), state.user_input[:50])

    except Exception as e:
        logger.error("RAG: ошибка поиска: %s", str(e))
        state.rag_context = []
        # Не ставим state.error — RAG не критичен, игра работает и без него

    return state