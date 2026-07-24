# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — RAG Loader (CLI)
# ─────────────────────────────────────────────────

"""
CLI-скрипт загрузки лора в векторную БД.

Использование:
    python -m bot.rag.loader                          # загрузить всё
    python -m bot.rag.loader --force                   # перезаписать всё
    python -m bot.rag.loader --dry-run                 # только показать, что будет
    python -m bot.rag.loader --file factions.txt       # только конкретный файл
    python -m bot.rag.loader --search "пурпурный туман" # поиск по готовым эмбедингам

Процесс:
    1. Сканирует data/lore/ — находит .txt, .md файлы
    2. Вычисляет MD5-хэш каждого файла
    3. Сравнивает с хэшами в БД (таблица document_chunks, extra_meta->>'file_hash')
    4. Новые/изменённые файлы: читает → чанкует → эмбедит → сохраняет
    5. Удалённые файлы: удаляет их чанки из БД
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Sequence
from pgvector.sqlalchemy import Vector

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from bot.models.base import SessionLocal
from bot.models.document_chunk import DocumentChunk
from bot.rag.chunker import Chunk, chunk_file
from bot.rag.embedder import embed_many

logger = logging.getLogger(__name__)

# ── Константы ────────────────────────────────────

DEFAULT_LORE_DIR = "/app/data/lore"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".rst", ".text"}


# ── Хэширование файлов ───────────────────────────

def file_hash(path: str) -> str:
    """MD5-хэш содержимого файла."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# ── Сканирование ──────────────────────────────────

def scan_lore_files(lore_dir: str) -> list[dict]:
    """
    Сканирует директорию, возвращает список файлов с метаданными.

    Returns:
        Список словарей: {path, name, hash, size, mtime}
    """
    lore_path = Path(lore_dir)
    if not lore_path.exists():
        logger.warning("Директория %s не найдена", lore_dir)
        return []

    files: list[dict] = []
    for entry in sorted(lore_path.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            fpath = str(entry)
            files.append({
                "path": fpath,
                "name": entry.name,
                "hash": file_hash(fpath),
                "size": entry.stat().st_size,
                "mtime": entry.stat().st_mtime,
            })
    return files


# ── Статус в БД ──────────────────────────────────

def load_known_hashes(db: Session) -> dict[str, int]:
    """
    Загружает из БД хэши уже загруженных файлов.
    Returns: {file_hash: количество_чанков}
    """
    rows = db.execute(
        sa_text("""
            SELECT extra_meta->>'file_hash' AS file_hash,
                   COUNT(*) AS chunk_count
            FROM document_chunks
            WHERE extra_meta->>'file_hash' IS NOT NULL
            GROUP BY file_hash
        """)
    ).fetchall()
    return {row.file_hash: row.chunk_count for row in rows}


def load_known_sources(db: Session) -> set[str]:
    """Загружает имена файлов, которые есть в БД."""
    rows = db.execute(
        sa_text('SELECT DISTINCT source FROM document_chunks')
    ).fetchall()
    return {row.source for row in rows}


# ── Сохранение в БД ──────────────────────────────

def save_chunks(db: Session, chunks: list[Chunk], vectors: list[list[float]],
                file_hash_value: str) -> int:
    """
    Сохраняет чанки с эмбедингами в БД.

    Args:
        db: Сессия SQLAlchemy
        chunks: Список чанков
        vectors: Список эмбедингов (той же длины, что и chunks)
        file_hash_value: MD5 хэш исходного файла

    Returns:
        Количество сохранённых чанков
    """
    if len(chunks) != len(vectors):
        raise ValueError(
            f"chunks({len(chunks)}) != vectors({len(vectors)})"
        )

    saved = 0
    for chunk, vector in zip(chunks, vectors):
        db_chunk = DocumentChunk(
            source=chunk.source,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            embedding=Vector(vector),
            extra_meta={
                "chapter": chunk.chapter,
                "char_count": chunk.char_count,
                "file_hash": file_hash_value,
                "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        db.add(db_chunk)
        saved += 1

    db.commit()
    return saved


def delete_source(db: Session, source: str) -> int:
    """Удаляет все чанки указанного источника."""
    deleted = db.query(DocumentChunk).filter(
        DocumentChunk.source == source
    ).delete()
    db.commit()
    return deleted


# ── Поиск (query) ────────────────────────────────

def search_similar(db: Session, query_embedding: list[float],
                   top_k: int = 5) -> list[dict]:
    """
    Поиск похожих чанков по cosine similarity.
    """
    # pgvector: <=> is cosine distance
    emb_str = json.dumps(query_embedding)
    rows = db.execute(
        sa_text(f"""
            SELECT source, chunk_index, content,
                   1 - (embedding <=> '{emb_str}'::vector) AS similarity,
                   extra_meta
            FROM document_chunks
            ORDER BY similarity DESC
            LIMIT :top_k
        """),
        {"top_k": top_k},
    ).fetchall()

    return [
        {
            "source": r.source,
            "chunk_index": r.chunk_index,
            "content": r.content[:200],
            "similarity": round(r.similarity, 4),
            "chapter": r.extra_meta.get("chapter") if r.extra_meta else None,
        }
        for r in rows
    ]


# ── CLI ──────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Загрузчик лора Samosbor в векторную БД (pgvector)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python -m bot.rag.loader
  python -m bot.rag.loader --force
  python -m bot.rag.loader --dry-run
  python -m bot.rag.loader --file factions.txt
  python -m bot.rag.loader --search "пурпурный туман"
        """,
    )
    parser.add_argument(
        "--lore-dir", default=DEFAULT_LORE_DIR,
        help="Директория с файлами лора (по умолч. %(default)s)",
    )
    parser.add_argument(
        "--file", "-f", type=str, default=None,
        help="Загрузить только конкретный файл (по имени)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Перезаписать все чанки (не только новые/изменённые)",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Показать, что будет сделано, без реальной загрузки",
    )
    parser.add_argument(
        "--search", "-s", type=str, default=None,
        help="Поиск по готовым эмбедингам (вводите текст запроса)",
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Количество результатов поиска (по умолч. %(default)s)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Подробный лог",
    )
    return parser


def cmd_load(args: argparse.Namespace) -> int:
    """Команда загрузки: сканирование → чанкинг → эмбединг → сохранение."""
    db = SessionLocal()

    try:
        # 1. Сканирование
        files = scan_lore_files(args.lore_dir)
        if not files:
            logger.warning("Нет файлов лора в %s", args.lore_dir)
            return 0

        # Фильтр по конкретному файлу
        if args.file:
            files = [f for f in files if f["name"] == args.file]
            if not files:
                logger.error("Файл '%s' не найден в %s", args.file, args.lore_dir)
                return 1

        # 2. Сравнение с БД
        known_hashes = load_known_hashes(db) if not args.force else {}
        known_sources = load_known_sources(db) if not args.force else set()

        to_process: list[dict] = []
        to_delete: set[str] = set()

        for f in files:
            if f["hash"] in known_hashes:
                logger.info("  ⏭  %s — без изменений (%d чанков)",
                            f["name"], known_hashes[f["hash"]])
                known_sources.discard(f["name"])
            else:
                to_process.append(f)

        # Файлы, которые были в БД, но исчезли из директории
        if not args.file:
            to_delete = known_sources

        # 3. Dry-run
        if args.dry_run:
            print(f"\n📋 Dry-run: {args.lore_dir}")
            print(f"   Всего файлов: {len(files)}")
            print(f"   Без изменений: {len(files) - len(to_process)}")
            print(f"   К загрузке:    {len(to_process)}")
            if to_delete:
                print(f"   К удалению:    {len(to_delete)} файлов")
                for src in sorted(to_delete):
                    print(f"     - {src}")
            print()
            for f in to_process:
                print(f"  → {f['name']} ({f['size']:,} bytes)")
            return 0

        # 4. Удаление устаревших
        if to_delete:
            for src in sorted(to_delete):
                deleted = delete_source(db, src)
                logger.info("  🗑  %s — удалено %d чанков", src, deleted)

        # 5. Загрузка
        total_chunks = 0
        total_chars = 0
        if to_process:
            # Удаляем старые чанки этого файла (если файл изменился)
            for f in to_process:
                old_count = delete_source(db, f["name"])
                if old_count:
                    logger.info("  ♻  %s — перезапись %d старых чанков",
                                f["name"], old_count)

            for f in to_process:
                file_start = time.time()
                logger.info("  📖 %s (%s bytes) — чанкинг…", f["name"],
                            _fmt_size(f["size"]))

                # Чанкинг
                chunks = chunk_file(f["path"])
                chunk_texts = [c.content for c in chunks]

                logger.info("     → %d чанков, ~%s всего",
                            len(chunks), _fmt_size(sum(c.char_count for c in chunks)))

                # Эмбединг
                logger.info("     🧠 эмбединг…")
                vectors = embed_many(chunk_texts)

                # Сохранение
                saved = save_chunks(db, chunks, vectors, f["hash"])

                elapsed = time.time() - file_start
                total_chunks += saved
                total_chars += sum(c.char_count for c in chunks)
                logger.info("     ✅ %d чанков сохранено за %.1fs", saved, elapsed)

        # 6. Итог
        print(f"\n{'='*50}")
        print(f"📊 Итого:")
        print(f"   Файлов обработано: {len(to_process)}")
        print(f"   Чанков сохранено:  {total_chunks}")
        print(f"   Всего символов:    {_fmt_size(total_chars)}")
        print(f"{'='*50}")

        return 0

    finally:
        db.close()


def cmd_search(args: argparse.Namespace) -> int:
    """Команда поиска: эмбединг запроса → pgvector similarity search."""
    from bot.rag.embedder import embed_text

    db = SessionLocal()
    try:
        logger.info("🔍 Поиск: '%s'", args.search)
        query_emb = embed_text(args.search)
        results = search_similar(db, query_emb, top_k=args.top_k)

        if not results:
            print("  (пусто — нет данных в векторной БД)")
            return 0

        print(f"\n🔍 Топ-{len(results)} результатов для '{args.search}':")
        print(f"{'='*60}")
        for i, r in enumerate(results, 1):
            print(f"\n{i}. [{r['source']}#{r['chunk_index']}] "
                  f"(сходство: {r['similarity']})")
            if r['chapter']:
                print(f"   📑 Глава: {r['chapter']}")
            print(f"   {r['content']}…")

        return 0
    finally:
        db.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=log_level,
        datefmt="%H:%M:%S",
    )

    if args.search:
        return cmd_search(args)
    else:
        return cmd_load(args)


def _fmt_size(n: int) -> str:
    """Форматирует число байт/символов в человекочитаемый вид."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    else:
        return f"{n / 1024 ** 2:.1f} MB"


if __name__ == "__main__":
    sys.exit(main())