# ─────────────────────────────────────────────────
# Person — базовая модель персонажа (для Player и NPC)
# Привязана к игровой сессии.
# ─────────────────────────────────────────────────

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession
    from bot.models.location import Location
    from bot.models.item import Item
    from bot.models.task import Task
    from bot.models.social import SocialRelation, InteractionHistory
    from bot.models.location import LocationVisitHistory


class Person(Base):
    """Персонаж игрового мира. Может быть Player (игрок) или NPC."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    name: Mapped[str] = mapped_column(String(128), comment="Имя")
    bio: Mapped[str] = mapped_column(Text, default="", comment="Биография")
    personality: Mapped[str] = mapped_column(
        Text, default="", comment="Характер"
    )
    appearance: Mapped[str] = mapped_column(
        Text, default="", comment="Внешность"
    )
    habits: Mapped[str] = mapped_column(Text, default="", comment="Привычки")
    current_location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("locations.id"), nullable=True, comment="Текущая локация"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", foreign_keys=[session_id]
    )
    current_location: Mapped[Optional["Location"]] = relationship(
        "Location", foreign_keys=[current_location_id]
    )

    # Предметы в инвентаре
    inventory: Mapped[list["Item"]] = relationship(
        "Item",
        foreign_keys="Item.owner_id",
        back_populates="owner",
    )

    # Задачи
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        foreign_keys="Task.assignee_id",
        back_populates="assignee",
    )

    # Социальный граф (кого знает этот персонаж)
    outgoing_relations: Mapped[list["SocialRelation"]] = relationship(
        "SocialRelation",
        foreign_keys="SocialRelation.from_person_id",
        back_populates="from_person",
    )

    # История взаимодействий
    interactions: Mapped[list["InteractionHistory"]] = relationship(
        "InteractionHistory",
        foreign_keys="InteractionHistory.person_id",
        back_populates="person",
    )

    # История посещений локаций
    location_visits: Mapped[list["LocationVisitHistory"]] = relationship(
        "LocationVisitHistory",
        foreign_keys="LocationVisitHistory.person_id",
        back_populates="person",
    )

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name='{self.name}')>"