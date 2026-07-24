# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Recursive Text Chunker
# ─────────────────────────────────────────────────

"""
Рекурсивный чанкер текста для лора.
Нарезает сырой текст на чанки фиксированного размера (в символах),
соблюдая естественные границы: абзацы → строки → предложения → символы.

Стратегия:
  1. Ищем заголовки глав (# Глава, Глава 1, === … ===)
  2. Рекурсивно бьём по разделителям от крупных к мелким
  3. Создаём перекрытие между соседними чанками
  4. Сохраняем мета-информацию (глава, источник)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

# ── Константы ─────────────────────────────────────

# Примерное соответствие: 1 токен ≈ 4 символа для русского текста
CHARS_PER_TOKEN = 4

# Целевой размер чанка в токенах → символах
TARGET_CHUNK_TOKENS = 500
TARGET_CHUNK_CHARS = TARGET_CHUNK_TOKENS * CHARS_PER_TOKEN  # 2000

# Перекрытие между чанками в токенах → символах
OVERLAP_TOKENS = 50
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN  # 200

# Минимальный размер чанка (меньше — склеиваем с предыдущим)
MIN_CHUNK_CHARS = TARGET_CHUNK_CHARS // 2  # 1000

# Максимальный размер чанка (больше — режем принудительно)
MAX_CHUNK_CHARS = TARGET_CHUNK_CHARS * 3 // 2  # 3000

# Порядок разделителей: от крупных к мелким
SEPARATORS = [
    re.compile(r'\n{3,}'),       # множественные пустые строки (раздел/глава)
    re.compile(r'\n{2}'),        # абзацы
    re.compile(r'(?<=\n)---+|===+'),  # горизонтальные разделители
    re.compile(r'\n'),           # строки
    re.compile(r'(?<=[.?!])\s+(?=[А-ЯA-Z])'),  # предложения
    re.compile(r'(?<=[;:])|\s+'),               # точка с запятой / двоеточие
    re.compile(r'\s+'),          # слова
]

# Паттерн для поиска заголовков глав
CHAPTER_PATTERNS = [
    re.compile(r'^#\s+(.+)$', re.MULTILINE),                     # Markdown H1
    re.compile(r'^##\s+(.+)$', re.MULTILINE),                    # Markdown H2
    re.compile(r'^###\s+(.+)$', re.MULTILINE),                   # Markdown H3
    re.compile(r'^(?:Глава|Гл\.|Chapter|Ch\.)\s+(\d+(?:\.\d+)?)', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^(?:Раздел|Часть|Part|Section)\s+(\d+)', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^={3,}\s*$', re.MULTILINE),                     # === separator
    re.compile(r'^-{3,}\s*$', re.MULTILINE),                     # --- separator
]


# ── Data ──────────────────────────────────────────

@dataclass
class Chunk:
    """Один чанк текста."""
    content: str
    chunk_index: int
    source: str
    chapter: str | None = None
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.content)


# ── Encoding ──────────────────────────────────────

_ENCODINGS = ['utf-8', 'cp1251', 'koi8-r', 'iso-8859-5', 'utf-16']


def detect_encoding(path: str) -> str:
    """Определяет кодировку файла перебором популярных."""
    raw = open(path, 'rb').read()
    for enc in _ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    # fallback с игнором ошибок
    return 'utf-8'


def read_file(path: str) -> str:
    """Читает файл с автоопределением кодировки."""
    encoding = detect_encoding(path)
    with open(path, 'r', encoding=encoding, errors='replace') as f:
        return f.read()


# ── Chapter detection ─────────────────────────────

def find_chapters(text: str) -> dict[int, str]:
    """
    Сканирует текст и возвращает словарь {позиция: название_главы}.

    Позиция — это offset в символах от начала текста.
    """
    chapters: dict[int, str] = {}
    for pat in CHAPTER_PATTERNS:
        for match in pat.finditer(text):
            pos = match.start()
            title = match.group(1).strip() if match.lastindex else match.group(0).strip()
            # Более специфичный паттерн имеет приоритет
            if pos not in chapters or len(pat.pattern) > 10:
                chapters[pos] = title
    return dict(sorted(chapters.items()))


def chapter_at_position(chapters: dict[int, str], pos: int) -> str | None:
    """Возвращает название главы для заданной позиции."""
    last: str | None = None
    for cpos, ctitle in chapters.items():
        if cpos > pos:
            break
        last = ctitle
    return last


# ── Recursive split ───────────────────────────────

def _split_at_separator(text: str, separators: list[re.Pattern]) -> list[str]:
    """
    Рекурсивно бьёт текст по разделителям.

    Сначала пробует первый разделитель (самый крупный).
    Если результирующие куски всё ещё больше MAX_CHUNK_CHARS —
    рекурсивно применяет следующий разделитель.
    """
    if not separators or len(text) <= MAX_CHUNK_CHARS:
        return [text]

    sep = separators[0]
    parts = sep.split(text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) <= 1:
        # Разделитель не найден — пробуем следующий уровень
        return _split_at_separator(text, separators[1:])

    result: list[str] = []
    for part in parts:
        if len(part) > MAX_CHUNK_CHARS:
            result.extend(_split_at_separator(part, separators[1:]))
        else:
            result.append(part)
    return result


def _merge_small_chunks(chunks: list[str], min_chars: int = MIN_CHUNK_CHARS) -> list[str]:
    """Склеивает слишком маленькие чанки с предыдущими."""
    if not chunks:
        return []

    merged: list[str] = []
    for chunk in chunks:
        if merged and len(merged[-1]) < min_chars:
            merged[-1] = merged[-1] + '\n\n' + chunk
        else:
            merged.append(chunk)

    # Если последний чанк слишком маленький — склеиваем с предпоследним
    if len(merged) > 1 and len(merged[-1]) < min_chars // 2:
        merged[-2] = merged[-2] + '\n\n' + merged[-1]
        merged.pop()

    return merged


def _add_overlap(chunks: list[str], overlap_chars: int = OVERLAP_CHARS) -> list[str]:
    """
    Добавляет перекрытие между соседними чанками.
    Берёт последние `overlap_chars` символов предыдущего чанка
    и добавляет их в начало следующего.
    """
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        curr = chunks[i]
        overlap = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
        result.append(overlap + '\n' + curr)
    return result


# ── Main API ──────────────────────────────────────

def chunk_text(
    text: str,
    source: str = 'unknown',
    target_chars: int = TARGET_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
    min_chars: int = MIN_CHUNK_CHARS,
) -> list[Chunk]:
    """
    Главная функция: нарезает текст на чанки.

    Args:
        text: Исходный текст
        source: Имя файла-источника (для мета-данных)
        target_chars: Целевой размер чанка в символах
        overlap_chars: Размер перекрытия в символах
        min_chars: Минимальный размер чанка

    Returns:
        Список Chunk с контентом и мета-информацией
    """
    # 1. Сброс глобальных констант (для тестирования/настройки)
    global MAX_CHUNK_CHARS, MIN_CHUNK_CHARS, OVERLAP_CHARS
    MAX_CHUNK_CHARS = target_chars * 3 // 2
    MIN_CHUNK_CHARS = min_chars
    OVERLAP_CHARS = overlap_chars

    # 2. Детект глав
    chapters = find_chapters(text)

    # 3. Разбивка на фрагменты
    parts = _split_at_separator(text, SEPARATORS)

    # 4. Склейка мелких фрагментов
    parts = _merge_small_chunks(parts, min_chars)

    # 5. Добавление перекрытия
    parts = _add_overlap(parts, overlap_chars)

    # 6. Сборка результата
    result: list[Chunk] = []
    offset = 0  # текущая позиция в исходном тексте
    for idx, part in enumerate(parts):
        chapter = chapter_at_position(chapters, offset)
        chunk = Chunk(
            content=part,
            chunk_index=idx,
            source=source,
            chapter=chapter,
        )
        result.append(chunk)
        # Смещаем offset для определения главы следующего чанка
        offset += len(part)

    return result


def chunk_file(
    path: str,
    target_chars: int = TARGET_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
    min_chars: int = MIN_CHUNK_CHARS,
) -> list[Chunk]:
    """
    Удобная обёртка: читает файл → chunk_text.

    Args:
        path: Путь к файлу
        target_chars: Целевой размер чанка в символах
        overlap_chars: Размер перекрытия в символах
        min_chars: Минимальный размер чанка

    Returns:
        Список Chunk
    """
    import os
    text = read_file(path)
    source = os.path.basename(path)
    return chunk_text(text, source=source, target_chars=target_chars,
                      overlap_chars=overlap_chars, min_chars=min_chars)
