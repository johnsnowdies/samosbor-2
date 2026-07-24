# ─────────────────────────────────────────────────
# Location — локация (в контексте игровой сессии)
# LocationConnection — M2M связь между локациями с описанием перехода
# ─────────────────────────────────────────────────

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession
    from bot.models.floor import Floor
    from bot.models.person import Person
    from bot.models.item import Item


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    name: Mapped[str] = mapped_column(
        Text, comment='Название ("Комната 312", "Коридор секции Б")'
    )
    description: Mapped[str] = mapped_column(
        Text, default="", comment="Текстовое описание"
    )
    floor_id: Mapped[int] = mapped_column(
        ForeignKey("floors.id"), comment="Этаж"
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="locations"
    )
    floor: Mapped["Floor"] = relationship(
        "Floor", back_populates="locations"
    )
    occupants: Mapped[list["Person"]] = relationship(
        "Person",
        foreign_keys="Person.current_location_id",
        back_populates="current_location",
    )
    items: Mapped[list["Item"]] = relationship(
        "Item",
        foreign_keys="Item.location_id",
        back_populates="location",
    )
    connections_from: Mapped[list["LocationConnection"]] = relationship(
        "LocationConnection",
        foreign_keys="LocationConnection.from_location_id",
        back_populates="from_location",
    )
    connections_to: Mapped[list["LocationConnection"]] = relationship(
        "LocationConnection",
        foreign_keys="LocationConnection.to_location_id",
        back_populates="to_location",
    )

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, name='{self.name}')>"


class LocationConnection(Base):
    """M2M связь между локациями с описанием перехода."""

    __tablename__ = "location_connections"

    from_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True
    )
    to_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True
    )
    description: Mapped[str] = mapped_column(
        Text, default="", comment="Описание перехода"
    )
    transition_type: Mapped[str] = mapped_column(
        Text, default="door",
        comment="Тип: door, stairs, elevator, vent, hatch, tunnel",
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Заперт ли переход"
    )

    # Связи
    from_location: Mapped["Location"] = relationship(
        "Location",
        foreign_keys=[from_location_id],
        back_populates="connections_from",
    )
    to_location: Mapped["Location"] = relationship(
        "Location",
        foreign_keys=[to_location_id],
        back_populates="connections_to",
    )

    def __repr__(self) -> str:
        return f"<LocationConnection({self.from_location_id} → {self.to_location_id})>"