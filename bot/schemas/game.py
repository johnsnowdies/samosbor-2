# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Pydantic схемы
# ─────────────────────────────────────────────────

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NPCAction(BaseModel):
    """Действие NPC в ответ на ход игрока."""
    npc_id: int
    action: str
    new_location_id: int | None = None


class GameAction(BaseModel):
    """Структурированный ответ LLM — вместо dirtyjson."""
    text: str = Field(description="Нарратив / описание сцены")
    actions: list[str] = Field(default_factory=list, description="Кнопки действий для игрока")
    items: list[str] = Field(default_factory=list, description="Изменения инвентаря")
    quests: list[str] = Field(default_factory=list, description="Новые / обновлённые квесты")
    game_over: bool = Field(default=False, description="Игра завершена")
    location: str | None = Field(default=None, description="Новая локация (если игрок перешёл)")
    location_id: int | None = Field(default=None, description="ID новой локации")
    image_prompt: str | None = Field(default=None, description="Промпт для генерации изображения (на английском)")
    npc_actions: list[NPCAction] = Field(default_factory=list, description="Действия NPC")


class GameState(BaseModel):
    """Состояние, проходящее через все ноды графа."""
    # Входные данные
    chat_id: int
    user_input: str
    session_id: int | None = None

    # Контекст из БД (заполняется в memory)
    player_id: int | None = None
    game_over: bool = False
    is_allowed: bool = True
    current_location_id: int | None = None
    current_location_name: str | None = None
    current_cycle: int = 1
    current_time: str = "08:00"

    # RAG контекст (заполняется в rag)
    rag_context: list[dict] = Field(default_factory=list)

    # История диалога (заполняется в memory)
    memory: list[dict] = Field(default_factory=list)

    # Промпт (заполняется в build_prompt)
    prompt: str | None = None

    # Ответ LLM (заполняется в llm_call)
    llm_response: str | None = None

    # Распарсенный ответ (заполняется в parse)
    parsed_response: GameAction | None = None

    # Ошибка (заполняется в guardrails или при падении)
    error: str | None = None

    # Дополнительные данные для передачи между нодами
    extra: dict[str, Any] = Field(default_factory=dict)