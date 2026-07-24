# ─────────────────────────────────────────────────
# NPC — неигровой персонаж
# ─────────────────────────────────────────────────

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.person import Person
    from bot.models.session import GameSession


class NPC(Base):
    """Неигровой персонаж. Принадлежит игровой сессии."""

    __tablename__ = "npcs"

    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    faction: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Фракция"
    )
    danger_level: Mapped[float] = mapped_column(
        Float, default=0.0, comment="0.0 - 1.0"
    )

    # Связи
    person: Mapped["Person"] = relationship(
        "Person", back_populates="npc", uselist=False
    )
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="npcs"
    )

    def __repr__(self) -> str:
        name = self.person.name if self.person else "?"
        return f"<NPC(id={self.person_id}, name='{name}', faction='{self.faction}')>"