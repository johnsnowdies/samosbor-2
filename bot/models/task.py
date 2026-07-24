# ─────────────────────────────────────────────────
# Task — задача / квест (в контексте игровой сессии)
# ─────────────────────────────────────────────────

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession
    from bot.models.person import Person


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    title: Mapped[str] = mapped_column(
        Text, comment='Название ("Найти воду", "Починить фильтр")'
    )
    description: Mapped[str] = mapped_column(
        Text, default="", comment="Подробное описание"
    )
    assignee_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), comment="Кому назначена"
    )
    location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("locations.id"), nullable=True, comment="Где выполнять"
    )
    location_hint: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment='"Где-то на 3-м этаже"'
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    reward: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment='Награда ("Пайка на неделю")'
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Саммари прогресса"
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="tasks"
    )
    assignee: Mapped["Person"] = relationship(
        "Person", foreign_keys=[assignee_id], back_populates="tasks"
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title='{self.title}')>"