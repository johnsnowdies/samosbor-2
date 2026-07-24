# ─────────────────────────────────────────────────
# Conversation — история чата (в контексте игровой сессии)
# ─────────────────────────────────────────────────

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    role: Mapped[str] = mapped_column(
        Text, comment="'user', 'assistant', 'system', 'npc'"
    )
    content: Mapped[str] = mapped_column(
        Text, comment="Текст сообщения"
    )
    cycle: Mapped[int] = mapped_column(
        Integer, default=1, comment="Игровой цикл"
    )
    tokens_used: Mapped[int] = mapped_column(
        Integer, default=0, comment="Потрачено токенов"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="conversations"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, role='{self.role}')>"