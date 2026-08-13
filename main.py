"""
Obsidian Voice Bot  v2
=======================
Telegram-бот, который:
  🎤 принимает ГОЛОСОВЫЕ -> расшифровка (Whisper API)
  💬 отвечает умно (LLM, OpenAI-совместимый)
  📥 ПИШЕТ ЗАДАЧУ В GOOGLE ТАБЛИЦУ "Hermes Inbox" (общий почтовый ящик с Hermes на компе)
  🗂 раскладывает по типам: идея / таск / купить / журнал (по ключевому слову)
  ⏰ ставит напоминания (пишет в таблицу + отвечает)
  💡 команда "разбери" -> ИИ дописывает уточнения/варианты

Секреты — ТОЛЬКО через переменные окружения (bot-host) или .env (локально).

Переменные:
  TELEGRAM_BOT_TOKEN        - токен @BotFather (обязательно)
  OPENAI_API_KEY            - ключ LLM/Whisper (обязательно)
  OPENAI_BASE_URL           - база API (опц.)
  CHAT_MODEL                - модель ответов (опц., gpt-4o-mini)
  WHISPER_MODEL             - модель расшифровки (опц., whisper-1)
  GOOGLE_SHEET_ID           - ID таблицы Hermes Inbox (обязательно для записи)
  GOOGLE_CREDENTIALS_JSON   - JSON сервисного аккаунта (для bot-host) ИЛИ
  GOOGLE_CREDENTIALS_FILE   - путь к файлу сервисного аккаунта
  NOTES_DIR                 - локальный резерв заметок (опц., ./notes)
  ALLOWED_USER_ID           - твой Telegram ID (опц., рекомендуется)
"""

import os
import io
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters,
)
from openai import OpenAI
from dotenv import load_dotenv

import sheets_writer

load_dotenv()
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("obsidian-voice-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
NOTES_DIR = os.getenv("NOTES_DIR", "./notes")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

os.makedirs(NOTES_DIR, exist_ok=True)

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("❌ Не задан TELEGRAM_BOT_TOKEN")
if not OPENAI_API_KEY:
    raise SystemExit("❌ Не задан OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

# Категории задач (по ключевому слову в начале сообщения)
CATEGORIES = {
    "идея": "💡 Идея",
    "идеи": "💡 Идея",
    "таск": "✅ Задача",
    "задача": "✅ Задача",
    "купить": "🛒 Купить",
    "купи": "🛒 Купить",
    "журнал": "📔 Журнал",
    "дневник": "📔 Журнал",
    "напомни": "⏰ Напоминание",
}


def allowed(update: Update) -> bool:
    if not ALLOWED_USER_ID:
        return True
    return str(update.effective_user.id) == str(ALLOWED_USER_ID)


def save_local_backup(raw, task):
    """Локальный резерв (если таблица недоступна)."""
    try:
        now = datetime.now()
        fn = now.strftime("%Y-%m-%d") + " " + task[:30].replace("/", "-") + ".md"
        with open(os.path.join(NOTES_DIR, fn), "w", encoding="utf-8") as f:
            f.write(f"# {task}\n\n{raw}\n")
    except Exception:
        pass


def inbox_write(raw, task, category="📝 Заметка"):
    """Пишет задачу в Google Таблицу + локальный резерв. Возвращает True/False."""
    full_task = f"{category} | {task}"
    ok = sheets_writer.add_inbox_row(raw, full_task, sheet_id=SHEET_ID)
    save_local_backup(raw, full_task)
    return ok


def detect_category(text: str):
    low = text.lower().strip()
    for key, label in CATEGORIES.items():
        if low.startswith(key):
            return label, text[len(key):].strip()
    return None, text


def transcribe(audio_bytes: bytes) -> str:
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "voice.ogg"
    result = client.audio.transcriptions.create(model=WHISPER_MODEL, file=audio_file)
    return result.text.strip()


def chat_reply(user_text: str) -> str:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": (
                "Ты — голосовой помощник пользователя. Отвечай кратко, по делу, "
                "на том же языке, что и пользователь.")},
            {"role": "user", "content": user_text},
        ],
    )
    return resp.choices[0].message.content.strip()


def expand_idea(text: str) -> str:
    """ИИ дописывает к идее уточнения и варианты."""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": (
                "Пользователь продиктовал идею. Кратко (3-4 пункта) допиши: "
                "в чём суть, кому полезно, какие риски, с чего начать. На том же языке.")},
            {"role": "user", "content": text},
        ],
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Обработчики
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    await update.message.reply_text(
        "👋 Я бот-почтальон в твою Google Таблицу «Hermes Inbox».\n\n"
        "• Голосовое — расшифрую и запишу задачу в таблицу.\n"
        "• Начни с <b>идея</b> / <b>таск</b> / <b>купить</b> / <b>журнал</b> — раскладу по папкам.\n"
        "• <b>напомни в 20:00 позвонить маме</b> — поставлю напоминание.\n"
        "• Команда /разбери — ИИ раскроет твою идею.\n"
        "• Команда /note &lt;текст&gt; — быстрая запись.\n"
        "Hermes дома увидит таблицу и выполнит задачу.",
        parse_mode="HTML",
    )


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Напиши после /note то, что сохранить.")
        return
    cat, clean = detect_category(text)
    label = cat or "📝 Заметка"
    ok = inbox_write(text, clean, label)
    await update.message.reply_text(
        ("✅ Записал в таблицу: " if ok else "⚠️ Таблица недоступна, сохранил локально: ")
        + f"{label} | {clean}"
    )


async def expand_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    text = " ".join(context.args) or (context.user_data.get("last_text", ""))
    if not text:
        await update.message.reply_text("Напиши после /разбери свою идею.")
        return
    await update.message.reply_text("💡 Раскрываю идею…")
    try:
        out = expand_idea(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        return
    await update.message.reply_text(out)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    await update.message.reply_text("🎤 Слушаю…")
    voice = await update.message.voice.get_file()
    audio_bytes = await voice.download_as_bytearray()
    try:
        text = transcribe(bytes(audio_bytes))
    except Exception as e:
        log.exception("Ошибка расшифровки")
        await update.message.reply_text(f"❌ Не удалось расшифровать: {e}")
        return
    if not text:
        await update.message.reply_text("🤔 Не услышал речи.")
        return
    context.user_data["last_text"] = text
    await process_text(update, text, raw=text)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    text = update.message.text
    context.user_data["last_text"] = text
    await process_text(update, text, raw=text)


async def process_text(update: Update, text: str, raw: str):
    low = text.lower().strip()

    # Напоминание
    if low.startswith("напомни"):
        rest = text[len("напомни"):].strip()
        ok = inbox_write(raw, rest, "⏰ Напоминание")
        await update.message.reply_text(
            ("⏰ Запомнил напоминание: " if ok else "⚠️ Сохранил локально: ") + rest)
        return

    # Явная просьба записать
    if low.startswith(("запиши", "сохрани", "note:")):
        clean = text.split(":", 1)[-1].strip() if ":" in text else text
        clean = clean.replace("запиши", "", 1).replace("сохрани", "", 1).strip()
        cat, body = detect_category(clean)
        label = cat or "📝 Заметка"
        ok = inbox_write(raw, body, label)
        await update.message.reply_text(
            ("✅ Записал в таблицу: " if ok else "⚠️ Таблица недоступна, локально: ")
            + f"{label} | {body}")
        return

    # Обычный диалог
    try:
        reply = chat_reply(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка ответа: {e}")
        return
    await update.message.reply_text(reply)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("разбери", expand_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Бот запущен. Таблица: %s", SHEET_ID or "(не задана)")
    app.run_polling()


if __name__ == "__main__":
    main()
