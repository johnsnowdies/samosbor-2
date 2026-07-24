# ─────────────────────────────────────────────────
# Player — игровой персонаж (главный герой сессии)
# ─────────────────────────────────────────────────

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class Player(Base):
    """Игровой персонаж. Один на сессию."""

    __tablename__ = "players"

    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )

    # Связи
    person: Mapped["Person"] = relationship(
        "Person", backref="player", uselist=False
    )
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="player"
    )

    def __repr__(self) -> str:
        return f"<Player(person_id={self.person_id}, session={self.session_id})>"