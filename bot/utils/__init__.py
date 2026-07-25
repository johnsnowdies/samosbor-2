# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Утилиты
# ─────────────────────────────────────────────────

"""Общие утилиты."""

import logging
import os

logger = logging.getLogger(__name__)


def clean_str(text: str) -> str:
    """
    Удаляет суррогатные пары из строки.
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def clean_dict(data: dict) -> dict:
    """Рекурсивно чистит все строки в словаре."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = clean_str(value)
        elif isinstance(value, dict):
            result[key] = clean_dict(value)
        elif isinstance(value, list):
            result[key] = [clean_dict(v) if isinstance(v, dict) else clean_str(v) if isinstance(v, str) else v for v in value]
        else:
            result[key] = value
    return result


# ── OpenAI клиент (без Langfuse, трейсинг вручную в llm_call) ──

def get_openai_client():
    """
    Создаёт обычный OpenAI-клиент.
    Langfuse трейсинг делается вручную в llm_call.py через Langfuse SDK.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=base_url)