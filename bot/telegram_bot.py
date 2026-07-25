# ─────────────────────────────────────────────────
# Samosbor AI Game v2 — Telegram Bot (polling)
# ─────────────────────────────────────────────────

"""
Telegram бот с polling.

Команды:
  /start    — новая игра
  /back     — повторить последний ответ
  /resend   — переслать последний запрос
  /balance  — баланс талонов
  /buy N    — купить N талонов (Telegram Stars)

Обычные сообщения — действия игрока, уходят в LangGraph граф.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from uuid import uuid4

from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from bot.models.base import SessionLocal
from bot.models.conversation import Conversation
from bot.models.session import GameSession
from bot.models.user import User
from sqlalchemy import select, desc

logger = logging.getLogger(__name__)

# ── ENV helpers ────────────────────────────────────

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default) or default


def _env_list(key: str, default: str = "") -> list[int]:
    raw = os.getenv(key, default)
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


# ── Config ─────────────────────────────────────────

COST_PER_MESSAGE = _env_int("COST_PER_MESSAGE", 1)
TRIAL_MESSAGES = _env_int("TRIAL_MESSAGES", 5)
STAR_PACKAGES = _env_list("STAR_PACKAGES", "50,100,200,500")
AI_IMAGE_BASE_URL = _env_str("AI_IMAGE_BASE_URL", "https://image.pollinations.ai/prompt/soviet-bunker-")
TOS_URL = _env_str("TOS_URL", "https://samosbor.one/tos.html")
PRIVACY_URL = _env_str("PRIVACY_URL", "https://samosbor.one/privacy.html")
CHANNEL_URL = _env_str("CHANNEL_URL", "https://t.me/samosbor_ai")
BOT_LANGUAGE = _env_str("BOT_LANGUAGE", "ru")


# ── DB helpers ─────────────────────────────────────

def get_user(db, chat_id: int) -> User | None:
    return db.execute(
        select(User).where(User.telegram_chat_id == chat_id)
    ).scalar_one_or_none()


def get_active_session(db, user: User) -> GameSession | None:
    return db.execute(
        select(GameSession)
        .where(GameSession.user_id == user.id, GameSession.game_over == False)
        .order_by(desc(GameSession.created_at))
        .limit(1)
    ).scalar_one_or_none()


# ── Image URL helper ───────────────────────────────

def _build_image_url(image_prompt: str) -> str | None:
    """Строит URL для генерации картинки и кодирует его."""
    if not image_prompt or not AI_IMAGE_BASE_URL:
        return None
    url = f"{AI_IMAGE_BASE_URL}{image_prompt}"
    return url


# ── Bot class ───────────────────────────────────────

class SamosborTelegramBot:
    """Telegram polling bot для игры «Самосбор»."""

    def __init__(self, token: str):
        self.token = token
        self._temporal_client = None
        self._build_application()

    def set_temporal_client(self, client):
        self._temporal_client = client

    def _build_application(self):
        app = (
            ApplicationBuilder()
            .token(self.token)
            .concurrent_updates(True)
            .post_init(self._post_init)
            .build()
        )

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("back", self.cmd_back))
        app.add_handler(CommandHandler("resend", self.cmd_resend))
        app.add_handler(CommandHandler("balance", self.cmd_balance))
        app.add_handler(CommandHandler("buy", self.cmd_buy))

        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        app.add_error_handler(self._error_handler)

        self.application = app

    async def _post_init(self, application: Application):
        """Регистрация команд в меню Telegram."""
        commands = [
            BotCommand(command="start", description="Новая игра"),
            BotCommand(command="back", description="Повторить последний ответ"),
            BotCommand(command="resend", description="Переслать последний запрос"),
            BotCommand(command="balance", description="Баланс талонов"),
            BotCommand(command="buy", description="Купить талоны"),
        ]
        await application.bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
        await application.bot.set_my_commands(commands)
        logger.info("Telegram: команды зарегистрированы в меню")

    # ── /start ──────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        db = SessionLocal()
        try:
            user = get_user(db, chat_id)
            if not user:
                user = User(
                    telegram_chat_id=chat_id,
                    balance=0,
                    trial_messages_left=TRIAL_MESSAGES,
                    is_allowed=True,
                )
                db.add(user)
                db.commit()
                logger.info("Telegram: новый пользователь chat_id=%s", chat_id)

            if not user.is_allowed:
                await self.reply(update, "❌ Доступ запрещён.")
                return

            # Приветственное сообщение (без упоминания моделей и цен)
            help_text = (
                "🚪 *Ты стоишь перед дверью в бесконечный дом.*\n\n"
                "Это бот для ролевой игры [Самосбор](https://neolurk.org/wiki/%D0%92%D1%81%D0%B5%D0%BB%D0%B5%D0%BD%D0%BD%D0%B0%D1%8F_%D0%A1%D0%B0%D0%BC%D0%BE%D1%81%D0%B1%D0%BE%D1%80%D0%B0) — "
                "бесконечной панельной многоэтажки, где фиолетовый туман и бурая слизь "
                "стали частью повседневности.\n\n"
                "🤖 ИИ генерирует сюжет, события и варианты действий.\n"
                "🏃‍♂️ Выбери предложенное действие или напиши, что хочешь сделать сам.\n"
                "🪦 Если персонаж умрёт — игра завершится.\n\n"
                "⚠️ Игра на ранней стадии разработки, возможны ошибки.\n"
                "⚠️ Если что-то пошло не так — /start перезапустит игру.\n\n"
                f"Подпишись на [канал]({CHANNEL_URL}) для новостей!"
            )

            await self.reply(update, help_text)

            # Автостарт игры
            await self._run_and_send(update, chat_id, "/start")
        finally:
            db.close()

    # ── /back ────────────────────────────────────────

    async def cmd_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        db = SessionLocal()
        try:
            user = get_user(db, chat_id)
            if not user:
                await self.reply(update, "Нет активной игры. Напишите /start.")
                return
            session = get_active_session(db, user)
            if not session:
                await self.reply(update, "Нет активной игры. Напишите /start.")
                return
            last = db.execute(
                select(Conversation)
                .where(Conversation.session_id == session.id, Conversation.role == "assistant")
                .order_by(desc(Conversation.created_at)).limit(1)
            ).scalar_one_or_none()
            await self.reply(update, last.content if last else "Нет предыдущего ответа.")
        finally:
            db.close()

    # ── /resend ────────────────────────────────────

    async def cmd_resend(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        db = SessionLocal()
        try:
            user = get_user(db, chat_id)
            if not user:
                await self.reply(update, "Нет активной игры. Напишите /start.")
                return
            session = get_active_session(db, user)
            if not session:
                await self.reply(update, "Нет активной игры. Напишите /start.")
                return
            last = db.execute(
                select(Conversation)
                .where(Conversation.session_id == session.id, Conversation.role == "user")
                .order_by(desc(Conversation.created_at)).limit(1)
            ).scalar_one_or_none()
            if not last:
                await self.reply(update, "Нет предыдущего запроса.")
                return
            await self._run_and_send(update, chat_id, last.content)
        finally:
            db.close()

    # ── /balance ──────────────────────────────────

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        await self.reply(update, "🎮 Биллинг временно отключён. Игра бесплатна.")

    # ── /buy ──────────────────────────────────────

    async def cmd_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.reply(update, "🎮 Биллинг временно отключён. Игра бесплатна.")

    # ── Текстовые сообщения ───────────────────────

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.edited_message:
            return

        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        if not text:
            return

        db = SessionLocal()
        try:
            user = get_user(db, chat_id)
            if not user:
                await self.reply(update, "Начните новую игру с /start.")
                return
            if not user.is_allowed:
                await self.reply(update, "❌ Доступ запрещён.")
                return
            if len(text) > 2000:
                await self.reply(update, "❌ Сообщение слишком длинное (макс. 2000 символов).")
                return

            await self._run_and_send(update, chat_id, text)
        finally:
            db.close()

    # ── Запуск графа с typing indicator ───────────

    async def _run_and_send(self, update: Update, chat_id: int, text: str):
        """Запускает граф и отправляет результат, поддерживая typing indicator."""
        async def _run() -> dict:
            return await self._run_graph(chat_id, text)

        result = await self._with_typing_indicator(update, _run)
        await self._send_result(update, result)

    async def _with_typing_indicator(self, update: Update, coro) -> dict:
        """
        Выполняет корутину, периодически отправляя typing indicator.
        Telegram сбрасывает статус через ~5 секунд, поэтому
        шлём chat_action каждые 4 секунды, пока задача не завершена.
        """
        chat = update.effective_chat

        async def _keep_typing():
            while True:
                try:
                    await chat.send_action(constants.ChatAction.TYPING)
                    await asyncio.sleep(4)
                except Exception:
                    break

        typing_task = asyncio.ensure_future(_keep_typing())
        try:
            result = await coro()
            return result
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def _run_graph(self, chat_id: int, text: str) -> dict:
        from bot.temporal.activities import run_game_graph

        if self._temporal_client:
            try:
                handle = await self._temporal_client.start_workflow(
                    "GameSessionWorkflow",
                    args=[chat_id, text],
                    id=f"game-{chat_id}-{uuid4()}",
                    task_queue="game-tasks",
                )
                return await handle.get_result()
            except Exception as e:
                logger.warning("Temporal fallback: %s", e)

        return await run_game_graph(chat_id, text)

    # ── Отправка результата ────────────────────────

    async def _send_result(self, update: Update, result: dict):
        if not result.get("success") and result.get("error"):
            await self.reply(update, f"❌ {result['error']}")
            return

        parts = []

        # Текст (нарратив)
        text = result.get("text") or "..."
        parts.append(text)

        # Предметы (инвентарь) — всегда в каждом сообщении
        items = result.get("items", [])
        parts.append("")
        if items:
            parts.append("*📦 Инвентарь:*")
            for item in items:
                parts.append(f"  • {item}")
        else:
            parts.append("*📦 Инвентарь:* пусто")

        # Квесты
        quests = result.get("quests", [])
        if quests:
            parts.append("")
            parts.append("*📜 Квесты:*")
            for q in quests:
                parts.append(f"  ▸ {q}")

        # Локация и время (Цикл вместо День)
        loc_parts = []
        location = result.get("location") or result.get("current_location")
        if location:
            loc_parts.append(f"📍 {location}")
        cycle = result.get("current_cycle", 1)
        cur_time = result.get("current_time", "08:00")
        loc_parts.append(f"⏱  Цикл {cycle}, {cur_time}")
        if loc_parts:
            parts.append("")
            parts.append(" | ".join(loc_parts))

        # Game over
        if result.get("game_over"):
            parts.append("")
            parts.append("💀 *ИГРА ЗАВЕРШЕНА*\nНапишите /start чтобы начать заново.")

        # Image — вставляем как невидимую ссылку [ ](url) для preview
        image_prompt = result.get("image_prompt")
        if image_prompt:
            img_url = _build_image_url(image_prompt)
            if img_url:
                parts.append(f" ")
                parts.append(f"[ ]({img_url})")

        # Собираем итоговое сообщение
        full_text = "\n".join(parts)

        # Кнопки действий
        actions = result.get("actions", [])
        markup = None
        if actions:
            markup = ReplyKeyboardMarkup(
                [[KeyboardButton(a)] for a in actions],
                resize_keyboard=True,
            )

        await self.reply(update, full_text, markup=markup)

        # NPC события отдельно
        npc_events = result.get("npc_events", [])
        if npc_events:
            for ev in npc_events:
                name = ev.get("npc_name") or f"NPC #{ev.get('npc_id', '?')}"
                action = ev.get("action", "")
                await self.reply(update, f"*{name}*: {action}")

    # ── Отправка сообщения ─────────────────────────

    async def reply(self, update: Update, text: str, markup=None, typing=False):
        if typing:
            await update.effective_chat.send_action(constants.ChatAction.TYPING)
        for i in range(0, len(text), 4096):
            try:
                await update.effective_message.reply_text(
                    text=text[i:i + 4096],
                    parse_mode=constants.ParseMode.MARKDOWN,
                    reply_markup=markup if i == 0 else None,
                )
            except Exception:
                await update.effective_message.reply_text(
                    text=text[i:i + 4096],
                    reply_markup=markup if i == 0 else None,
                )

    # ── Ошибки ─────────────────────────────────────

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error("Telegram error: %s", context.error)

    # ── Запуск ─────────────────────────────────────

    def run(self):
        """Запуск polling в новом asyncio loop (для работы в thread)."""
        logger.info("Telegram: запуск polling...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        finally:
            loop.close()

    async def _run_async(self):
        """Асинхронный запуск polling без signal handlers (не run_polling)."""
        await self.application.initialize()
        await self.application.updater.start_polling()
        await self.application.start()
        logger.info("Telegram: polling запущен")
        # Держим поток живым
        while True:
            await asyncio.sleep(3600)