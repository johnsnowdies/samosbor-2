# ─────────────────────────────────────────────────
# User — пользователь Telegram (не путать с игровым персонажем)
# ─────────────────────────────────────────────────

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession


class User(Base):
    """Пользователь Telegram: баланс, триал, настройки."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, comment="Telegram chat_id"
    )
    balance: Mapped[int] = mapped_column(
        Integer, default=0, comment="Талоны"
    )
    trial_messages_left: Mapped[int] = mapped_column(
        Integer, default=5, comment="Бесплатные сообщения (триал)"
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Администратор"
    )
    is_allowed: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="Разрешено ли пользоваться ботом"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    game_sessions: Mapped[list["GameSession"]] = relationship(
        "GameSession", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, chat_id={self.telegram_chat_id})>"