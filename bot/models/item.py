# ─────────────────────────────────────────────────
# Item — предмет (в контексте игровой сессии)
# ─────────────────────────────────────────────────

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession
    from bot.models.person import Person
    from bot.models.location import Location


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    name: Mapped[str] = mapped_column(Text, comment="Название")
    description: Mapped[str] = mapped_column(
        Text, default="", comment="Описание"
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id"), nullable=True,
        comment="У кого сейчас (если у персонажа)",
    )
    location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("locations.id"), nullable=True,
        comment="Где лежит (если не у персонажа)",
    )
    is_equipped: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Экипирован ли"
    )
    item_type: Mapped[str] = mapped_column(
        Text, default="misc",
        comment="Тип: weapon, armour, food, tool, medical, document, key, misc",
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="items"
    )
    owner: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[owner_id], back_populates="inventory"
    )
    location: Mapped[Optional["Location"]] = relationship(
        "Location", foreign_keys=[location_id], back_populates="items"
    )

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, name='{self.name}')>"