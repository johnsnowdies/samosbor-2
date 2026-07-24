# ─────────────────────────────────────────────────
# SocialRelation — социальный граф (в контексте сессии)
# InteractionHistory — история взаимодействий
# LocationVisitHistory — история посещений локаций
# ─────────────────────────────────────────────────

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

if TYPE_CHECKING:
    from bot.models.session import GameSession
    from bot.models.person import Person
    from bot.models.location import Location


class SocialRelation(Base):
    """Отношение одного персонажа к другому."""

    __tablename__ = "social_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    from_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    to_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    affinity: Mapped[float] = mapped_column(
        Float,
        comment="Отношение: -1.0 (ненависть) .. 1.0 (обожание), 0 = нейтрально",
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="social_relations"
    )
    from_person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[from_person_id],
        back_populates="outgoing_relations",
    )
    to_person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[to_person_id]
    )

    def __repr__(self) -> str:
        return f"<SocialRelation({self.from_person_id} → {self.to_person_id}: {self.affinity})>"


class InteractionHistory(Base):
    """История взаимодействий между персонажами."""

    __tablename__ = "interaction_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"),
        comment="Кто взаимодействовал",
    )
    target_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"),
        comment="С кем взаимодействовал",
    )
    event: Mapped[str] = mapped_column(
        Text, comment="Текстовое описание события"
    )
    cycle: Mapped[int] = mapped_column(Integer, comment="Игровой цикл")
    time: Mapped[str] = mapped_column(
        Text, comment="Игровое время HH:MM"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="interactions"
    )
    person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[person_id], back_populates="interactions"
    )
    target_person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[target_person_id]
    )

    def __repr__(self) -> str:
        return f"<InteractionHistory(id={self.id})>"


class LocationVisitHistory(Base):
    """История посещений локаций персонажем."""

    __tablename__ = "location_visit_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        comment="Игровая сессия",
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE")
    )
    visit_reason: Mapped[str] = mapped_column(
        Text, default="", comment="Причина и обстоятельства"
    )
    cycle: Mapped[int] = mapped_column(Integer)
    time: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Связи
    session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="location_visits"
    )
    person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[person_id], back_populates="location_visits"
    )
    location: Mapped["Location"] = relationship(
        "Location", foreign_keys=[location_id]
    )

    def __repr__(self) -> str:
        return f"<LocationVisitHistory(id={self.id})>"