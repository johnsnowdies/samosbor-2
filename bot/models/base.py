# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — SQLAlchemy Base + Engine
# ─────────────────────────────────────────────────

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Базовый класс с Python-side defaults.

    SQLAlchemy 2.0.36+ не устанавливает Python-дефолты при создании объекта
    (только при INSERT). Добавляем свои defaults прямо в __init__.

    ВАЖНО: не вызываем super().__init__, т.к. DeclarativeBase не имеет
    собственного __init__, а SQLAlchemy генерирует __init__ для каждого
    класса через метакласс — наш __init__ его переопределяет.
    """

    def __init__(self, **kwargs: object) -> None:
        # Применяем Python-side defaults из mapped_column/default
        for col in self.__mapper__.columns:
            if col.key not in kwargs and col.default is not None:
                raw = col.default.arg
                if callable(raw):
                    # SQLAlchemy 2.0.36+ оборачивает callable так,
                    # что он ожидает ExecutionContext (ctx)
                    try:
                        kwargs[col.key] = raw()
                    except TypeError:
                        kwargs[col.key] = raw(None)
                else:
                    kwargs[col.key] = raw
        # Устанавливаем атрибуты напрямую (через сеттеры SQLAlchemy),
        # чтобы корректно инициализировать InstanceState
        for key, value in kwargs.items():
            setattr(self, key, value)


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('POSTGRES_USER', 'samosbor')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'changeme')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'samosbor')}",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()