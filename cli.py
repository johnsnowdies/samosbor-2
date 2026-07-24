#!/usr/bin/env python3
# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — CLI для проверки игры
# Диалоговый режим, fake tgid, напрямую через LangGraph
# ─────────────────────────────────────────────────

"""
Простой CLI для тестирования игровых механик.

Использование:
  python cli.py                  # интерактивный режим
  python cli.py --tgid 12345     # с указанием chat_id
  python cli.py --single "текст" # однократный запрос

Команды внутри чата:
  /start      — начать новую игру
  /session    — показать текущую сессию
  /help       — справка
  /exit       — выход

Требуется:
  - Работающий Docker Compose (БД, OpenRouter API-ключ в .env)
  - Запуск из контейнера: docker compose exec bot python cli.py
"""

from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("cli").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("bot").setLevel(logging.WARNING)

logger = logging.getLogger("cli")


# ── Импорты проекта ──────────────────────────────

from bot.schemas.game import GameState
from bot.langgraph.graph import get_game_graph
from bot.models.base import SessionLocal
from bot.models.user import User
from bot.models.session import GameSession
from bot.models.player import Player
from bot.models.person import Person
from bot.models.location import Location
from bot.models.npc import NPC
from bot.models.conversation import Conversation
from sqlalchemy import select, func


# ── ANSI цвета ────────────────────────────────────

class Style:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    RESET = "\033[0m"
    GRAY = "\033[90m"
    SEPARATOR = "─" * 50


# ── Вспомогательные функции ──────────────────────

def print_header():
    print()
    print(f"{Style.BOLD}{Style.MAGENTA} ╔════ Самосбор AI Game v2 — CLI ════╗{Style.RESET}")
    print()
    print(f"{Style.DIM} Команды: /start /session /help /exit{Style.RESET}")
    print()


def show_session(db, chat_id: int):
    """Показывает информацию о текущей сессии."""
    user = db.execute(
        select(User).where(User.telegram_chat_id == chat_id)
    ).scalar_one_or_none()

    if not user:
        print(f"{Style.YELLOW}Нет пользователя. Напишите /start.{Style.RESET}")
        return

    session = db.execute(
        select(GameSession)
        .where(GameSession.user_id == user.id, GameSession.game_over == False)
        .order_by(GameSession.created_at.desc())
    ).scalar_one_or_none()

    if not session:
        print(f"{Style.YELLOW}Нет активной сессии. Напишите /start.{Style.RESET}")
        return

    player = db.execute(select(Player).where(Player.session_id == session.id)).scalar_one_or_none()

    person_name = "—"
    location_name = "—"
    npc_count = 0

    if player:
        person = db.get(Person, player.person_id)
        if person:
            person_name = person.name
            if person.current_location_id:
                loc = db.get(Location, person.current_location_id)
                if loc:
                    location_name = loc.name
                    npc_count = db.execute(
                        select(func.count(NPC.person_id))
                        .join(Person, NPC.person_id == Person.id)
                        .where(Person.current_location_id == loc.id, Person.session_id == session.id)
                    ).scalar() or 0

    msg_count = db.execute(
        select(func.count(Conversation.id)).where(Conversation.session_id == session.id)
    ).scalar() or 0

    created = session.created_at.strftime('%Y-%m-%d %H:%M') if session.created_at else '—'
    status = "✅ активна" if not session.game_over else "❌ завершена"

    print(f"{Style.CYAN}📋 Сессия #{session.id}{Style.RESET}")
    print(f"  Игрок:    {Style.BOLD}{person_name}{Style.RESET}")
    print(f"  Локация:  {location_name}")
    print(f"  Цикл:     {session.current_cycle}, время: {session.current_time}")
    print(f"  NPC рядом: {npc_count}")
    print(f"  Сообщений: {msg_count}")
    print(f"  Статус:   {status}")
    print(f"  Создана:  {created}")


def show_help():
    print(f"{Style.CYAN}Команды:{Style.RESET}")
    print(f"  {Style.BOLD}/start{Style.RESET}    — начать новую игру")
    print(f"  {Style.BOLD}/session{Style.RESET}  — состояние сессии")
    print(f"  {Style.BOLD}/help{Style.RESET}     — справка")
    print(f"  {Style.BOLD}/exit{Style.RESET}     — выход")
    print()
    print("Любой другой текст — действие для игрового мастера.")


def print_response(state: GameState):
    """Красиво выводит ответ игры."""
    if state.error:
        print(f"\n{Style.RED}❌ {state.error}{Style.RESET}\n")
        return

    action = state.parsed_response
    if not action:
        if state.llm_response:
            print(f"\n{Style.YELLOW}⚠️  Не удалось распарсить:{Style.RESET}")
            print(f"  {state.llm_response[:300]}")
        return

    # Текст
    if action.text:
        for p in action.text.split("\n"):
            p = p.strip()
            if p:
                print(f"\n  {p}")

    # Действия
    if action.actions:
        print(f"\n{Style.GREEN}🎯 Действия:{Style.RESET}")
        for i, a in enumerate(action.actions, 1):
            print(f"  {i}. {a}")

    # Предметы
    if action.items:
        print(f"\n{Style.YELLOW}📦 Инвентарь:{Style.RESET}")
        for item in action.items:
            print(f"  • {item}")

    # Квесты
    if action.quests:
        print(f"\n{Style.CYAN}📜 Квесты:{Style.RESET}")
        for q in action.quests:
            print(f"  ▸ {q}")

    # Локация и время
    loc_parts = []
    if action.location:
        loc_parts.append(f"📍 {action.location}")
    if state.current_time and state.current_cycle:
        loc_parts.append(f"⏱️  День {state.current_cycle}, {state.current_time}")
    if loc_parts:
        print(f"\n{Style.GRAY}{' | '.join(loc_parts)}{Style.RESET}")

    # NPC события
    npc_events = state.extra.get("npc_events", [])
    if npc_events:
        print(f"\n{Style.MAGENTA}👥 NPC:{Style.RESET}")
        for ev in npc_events:
            name = ev.get("npc_name", f"NPC #{ev.get('npc_id')}")
            print(f"  {Style.DIM}{name}:{Style.RESET} {ev.get('action', '')}")

    if action.game_over:
        print(f"\n{Style.RED}{Style.BOLD}💀 ИГРА ЗАВЕРШЕНА{Style.RESET}")

    if action.image_prompt:
        print(f"\n{Style.GRAY}🖼️  {action.image_prompt}{Style.RESET}")

    print()


# ── Основной цикл ──────────────────────────────────

def main_loop(chat_id: int = 666):
    """Интерактивный диалог."""
    print_header()
    print(f"{Style.GRAY}chat_id: {chat_id}{Style.RESET}\n")

    db = SessionLocal()
    graph = get_game_graph()

    try:
        while True:
            try:
                text = input(f"{Style.BOLD}{Style.GREEN}Вы ⤻{Style.RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{Style.CYAN}Пока!{Style.RESET}")
                break

            if not text:
                continue

            if text == "/exit":
                print(f"{Style.CYAN}Пока!{Style.RESET}")
                break
            if text == "/help":
                show_help()
                print(f"{Style.GRAY}{Style.SEPARATOR}{Style.RESET}")
                continue
            if text == "/session":
                show_session(db, chat_id)
                print(f"{Style.GRAY}{Style.SEPARATOR}{Style.RESET}")
                continue

            state = GameState(chat_id=chat_id, user_input=text)
            try:
                result = graph.invoke(state)
                print_response(GameState(**result))
            except Exception as e:
                print(f"\n{Style.RED}❌ Ошибка: {e}{Style.RESET}")
                import traceback
                traceback.print_exc()

            print(f"{Style.GRAY}{Style.SEPARATOR}{Style.RESET}")

    finally:
        db.close()


# ── Однократный запрос ────────────────────────────

def single_run(text: str, chat_id: int = 666):
    """Однократный запрос к игре."""
    db = SessionLocal()
    graph = get_game_graph()

    try:
        state = GameState(chat_id=chat_id, user_input=text)
        result = graph.invoke(state)
        print_response(GameState(**result))
    finally:
        db.close()


# ── Точка входа ───────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samosbor AI Game v2 — CLI")
    parser.add_argument("--tgid", type=int, default=666, help="Telegram chat_id")
    parser.add_argument("--single", type=str, help="Однократный запрос")
    args = parser.parse_args()

    if args.single:
        single_run(args.single, args.tgid)
    else:
        main_loop(args.tgid)