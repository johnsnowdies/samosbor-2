# ─────────────────────────────────────────────────
# GameSession — игровая сессия
# Каждая новая игра = новая сессия.
# Все сущности (NPC, локации, предметы, квесты) привязаны к session_id.
# ─────────────────────────────────────────────────

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.user import User
    from bot.models.person import Person
    from bot.models.player import Player
    from bot.models.npc import NPC
    from bot.models.floor import Floor
    from bot.models.location import Location, LocationConnection
    from bot.models.item import Item
    from bot.models.task import Task
    from bot.models.social import SocialRelation, InteractionHistory, LocationVisitHistory
    from bot.models.conversation import Conversation


class GameSession(Base):
    """Игровая сессия. Привязывает пользователя к игровому миру."""

    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), comment="Владелец сессии"
    )
    game_over: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Игра завершена"
    )
    current_cycle: Mapped[int] = mapped_column(
        Integer, default=1, comment="Игровой день (1..365)"
    )
    current_time: Mapped[str] = mapped_column(
        String(5), default="08:00", comment="Игровое время HH:MM"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    user: Mapped["User"] = relationship(
        "User", back_populates="game_sessions"
    )

    # Игрок (главный персонаж этой сессии)
    player: Mapped["Player"] = relationship(
        "Player", back_populates="session", uselist=False, passive_deletes=True
    )

    # NPC
    npcs: Mapped[list["NPC"]] = relationship(
        "NPC", back_populates="session", passive_deletes=True
    )

    # Локации и этажи
    floors: Mapped[list["Floor"]] = relationship(
        "Floor", back_populates="session", passive_deletes=True
    )
    locations: Mapped[list["Location"]] = relationship(
        "Location", back_populates="session", passive_deletes=True
    )

    # Предметы
    items: Mapped[list["Item"]] = relationship(
        "Item", back_populates="session", passive_deletes=True
    )

    # Задачи
    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="session", passive_deletes=True
    )

    # Социальный граф
    social_relations: Mapped[list["SocialRelation"]] = relationship(
        "SocialRelation", back_populates="session", passive_deletes=True
    )

    # История
    interactions: Mapped[list["InteractionHistory"]] = relationship(
        "InteractionHistory", back_populates="session", passive_deletes=True
    )
    location_visits: Mapped[list["LocationVisitHistory"]] = relationship(
        "LocationVisitHistory", back_populates="session", passive_deletes=True
    )

    # История чата
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="session", passive_deletes=True
    )

    # Связи локаций
    location_connections: Mapped[list["LocationConnection"]] = relationship(
        "LocationConnection", back_populates="session", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<GameSession(id={self.id}, user={self.user_id}, game_over={self.game_over})>"