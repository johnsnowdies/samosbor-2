# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — pytest fixtures
# ─────────────────────────────────────────────────

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from bot.models import Base

# Берём DATABASE_URL из окружения, либо ставим тестовую БД
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://samosbor:changeme@postgres:5432/samosbor_test",
)


@pytest.fixture(scope="session")
def engine():
    """Создаём engine для тестовой БД."""
    e = create_engine(TEST_DATABASE_URL, echo=False)
    # Включаем pgvector extension
    with e.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    # Создаём схему
    Base.metadata.create_all(bind=e)
    yield e
    Base.metadata.drop_all(bind=e)
    e.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    """Транзакционный db_session с откатом после теста."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()