# ─────────────────────────────────────────────────
# Floor — этаж Гигахрущёвки (в контексте игровой сессии)
# ─────────────────────────────────────────────────

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession


class Floor(Base):
    __tablename__ = "floors"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    name: Mapped[str] = mapped_column(
        String(128), comment='Название ("этаж 345", "партийный", "тёмный")'
    )
    description: Mapped[str] = mapped_column(
        Text, default="", comment="Описание этажа"
    )
    is_inhabited: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="Обитаем ли этаж"
    )
    danger_level: Mapped[float] = mapped_column(
        Float, default=0.0, comment="Уровень опасности 0.0 - 1.0"
    )
    is_contaminated: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Загрязнён Самосбором"
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="floors"
    )
    locations: Mapped[list["Location"]] = relationship(
        "Location", back_populates="floor"
    )

    def __repr__(self) -> str:
        return f"<Floor(id={self.id}, name='{self.name}')>"