#!/usr/bin/env python3
# ─────────────────────────────────────────────────
# Список моделей в Ollama
# ─────────────────────────────────────────────────

"""Выводит список загруженных моделей в Ollama с размером."""

import urllib.request
import json
import sys

OLLAMA_URL = "http://ollama:11434/api/tags"

try:
    req = urllib.request.Request(OLLAMA_URL)
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read())
    models = data.get("models", [])

    if not models:
        print("Нет загруженных моделей. Загрузите: ollama pull <model>")
        sys.exit(0)

    print(f"Моделей в Ollama: {len(models)}\n")
    for m in sorted(models, key=lambda x: x.get("name", "")):
        name = m.get("name", "?")
        size = m.get("size", 0)
        modified = m.get("modified_at", "?")[:19].replace("T", " ")
        size_gb = size / 1024**3
        print(f"  {name}")
        print(f"    Размер: {size_gb:.1f} GB")
        print(f"    Загружена: {modified}")
        print()

except json.JSONDecodeError:
    print("Ошибка: не удалось распарсить ответ Ollama")
    sys.exit(1)
except Exception as e:
    print(f"Ошибка подключения к Ollama: {e}")
    sys.exit(1)