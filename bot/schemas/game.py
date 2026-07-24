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


class SocialChange(BaseModel):
    """Изменение отношения между персонажами."""
    npc: str = Field(description="Имя NPC, чьё отношение меняется")
    target: str = Field(description="К кому меняется отношение (имя NPC или 'игрок')")
    delta: float = Field(description="Изменение affinity: -1.0..1.0", ge=-1.0, le=1.0)
    reason: str = Field(default="", description="Причина изменения (для логирования)")


class ValidationResult(BaseModel):
    """Результат проверки действия игрока (LLM guardrails)."""
    allowed: bool = Field(description="Действие разрешено?")
    reason: str = Field(default="", description="Объяснение, если запрещено")


class NpcData(BaseModel):
    """Данные NPC для создания в БД."""
    name: str
    bio: str = ""
    personality: str = ""
    appearance: str = ""
    habits: str = ""
    faction: str | None = None
    danger_level: float = 0.0
    location: str | None = None  # название локации, где находится NPC


class FloorData(BaseModel):
    """Данные этажа."""
    name: str
    danger_level: float = 0.0
    is_contaminated: bool = False


class LocationData(BaseModel):
    """Данные локации."""
    name: str
    description: str = ""
    floor: str = ""  # название этажа


class NpcRelationData(BaseModel):
    """Отношения между NPC."""
    npc_name_from: str
    npc_name_to: str
    affinity: float = 0.0  # -1.0 .. 1.0


class LocationConnectionData(BaseModel):
    """Связь между локациями (для генерации мира)."""
    from_location: str = Field(description="Название исходной локации")
    to_location: str = Field(description="Название целевой локации")
    description: str = Field(description="Описание перехода (дверь, лестница, люк...)")
    transition_type: str = Field(default="door", description="door, stairs, elevator, vent, hatch, tunnel")
    is_locked: bool = False


class LocationGenData(BaseModel):
    """Генерация/расширение локаций — ответ LLM."""
    locations: list[LocationData] = Field(default_factory=list, description="Новые локации")
    connections: list[LocationConnectionData] = Field(default_factory=list, description="Связи между локациями")
    npcs: list[NpcData] = Field(default_factory=list, description="Новые NPC для этих локаций")
    npc_relations: list[NpcRelationData] = Field(default_factory=list, description="Отношения между NPC")


class FactCheckResult(BaseModel):
    """Результат проверки ответа LLM на фактологическую корректность."""
    is_coherent: bool = Field(description="Всё ли корректно?")
    issues: list[str] = Field(default_factory=list, description="Найденные проблемы")
    corrected_text: str | None = Field(default=None, description="Исправленный текст (если issues)")


class WorldData(BaseModel):
    """Данные для инициализации игрового мира.
    Возвращается LLM при /start, используется для создания сущностей в БД.
    """
    player_name: str
    player_bio: str = ""
    player_appearance: str = ""
    player_personality: str = ""
    player_habits: str = ""
    floors: list[FloorData] = Field(default_factory=list, description="Этажи (минимум 1)")
    start_location: str = Field(description="Стартовая локация игрока")
    start_location_description: str = ""
    locations: list[LocationData] = Field(default_factory=list, description="Стартовая локация + соседние (2-4 локации)")
    connections: list[LocationConnectionData] = Field(default_factory=list, description="Связи между локациями")
    items: list[str] = Field(default_factory=list, description="Стартовые предметы игрока")
    npcs: list[NpcData] = Field(default_factory=list, description="NPC в мире")
    npc_relations: list[NpcRelationData] = Field(default_factory=list, description="Отношения между NPC")
    quests: list[str] = Field(default_factory=list, description="Стартовые квесты")


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
    social_changes: list[SocialChange] = Field(default_factory=list, description="Изменения отношений между персонажами")
    world: WorldData | None = Field(default=None, description="Данные мира (только при /start)")


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

    # Валидация действия (заполняется в validate_action)
    validation_result: ValidationResult | None = None

    # Данные для генерации/расширения мира
    world_gen: LocationGenData | None = None

    # Результат факт-чека
    fact_check: FactCheckResult | None = None

    # Флаги для потока графа
    is_new_game: bool = Field(default=False, description="/start или нет")
    location_changed: bool = Field(default=False, description="Игрок сменил локацию")
    floor_changed: bool = Field(default=False, description="Игрок сменил этаж")

    # Ошибка (заполняется в guardrails или при падении)
    error: str | None = None

    # Дополнительные данные для передачи между нодами
    extra: dict[str, Any] = Field(default_factory=dict)