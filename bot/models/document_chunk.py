# ─────────────────────────────────────────────────
# DocumentChunk — чанки лора для RAG (pgvector)
# ─────────────────────────────────────────────────

from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(
        Text, comment="Название книги / фанфика"
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, comment="Номер чанка в документе"
    )
    content: Mapped[str] = mapped_column(
        Text, comment="Текст чанка"
    )
    embedding: Mapped[Vector] = mapped_column(
        Vector(1536), comment="Эмбединг (размерность зависит от модели)"
    )
    extra_meta: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="Дополнительные метаданные"
    )

    __table_args__ = (
        Index(
            "idx_document_chunks_embedding",
            embedding,
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_document_chunks_source", source),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, source='{self.source}', chunk={self.chunk_index})>"