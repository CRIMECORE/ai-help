"""
Obsidian Voice Bot  v3
=======================
Telegram-бот "почтальон" в Google Таблицу "Hermes Inbox".

Поведение:
  🎤 Голосовое / 💬 Текст -> расшифровка (Whisper) + умный ответ (LLM)
  📝 Заметка (идея/таск/купить/журнал) -> сразу пишет в таблицу (status=new)
  ⚙️ РЕАЛЬНОЕ ДЕЙСТВИЕ (создать папку, запустить, удалить и т.п.,
     НЕ связанное с заметкой и НЕ просто вопрос) ->
       бот шлёт подтверждение: "Я понял так: <описание>" + кнопки [Да] [Нет]
       Да -> пишет в таблицу (status=confirm)
       Нет -> ничего не пишет, не делает
  ❓ Просто вопрос -> отвечает, ничего не пишет

Секреты — ТОЛЬКО через переменные окружения (bot-host) или .env (локально).

Переменные:
  TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, OPENAI_BASE_URL, CHAT_MODEL, WHISPER_MODEL,
  GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON (или GOOGLE_CREDENTIALS_FILE),
  NOTES_DIR, ALLOWED_USER_ID, APPROVE_CHAT_ID (твой Telegram ID для подтверждений)
"""

import os
import io
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters, CallbackQueryHandler,
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
APPROVE_CHAT_ID = os.getenv("APPROVE_CHAT_ID", ALLOWED_USER_ID)

os.makedirs(NOTES_DIR, exist_ok=True)

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("❌ Не задан TELEGRAM_BOT_TOKEN")
if not OPENAI_API_KEY:
    raise SystemExit("❌ Не задан OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

CATEGORIES = {
    "идея": "💡 Идея", "идеи": "💡 Идея",
    "таск": "✅ Задача", "задача": "✅ Задача",
    "купить": "🛒 Купить", "купи": "🛒 Купить",
    "журнал": "📔 Журнал", "дневник": "📔 Журнал",
    "напомни": "⏰ Напоминание",
}


def allowed(update: Update) -> bool:
    # Диагностика: логируем ID и пускаем всех (пока тестируем)
    uid = update.effective_user.id if update.effective_user else None
    log.info("Входящее сообщение от user_id=%s (ALLOWED_USER_ID=%s)", uid, ALLOWED_USER_ID)
    return True


def save_local_backup(raw, task):
    try:
        now = datetime.now()
        fn = now.strftime("%Y-%m-%d") + " " + task[:30].replace("/", "-") + ".md"
        with open(os.path.join(NOTES_DIR, fn), "w", encoding="utf-8") as f:
            f.write(f"# {task}\n\n{raw}\n")
    except Exception:
        pass


def inbox_write(raw, task, category="📝 Заметка", status="new"):
    full = f"{category} | {task}"
    ok = sheets_writer.add_inbox_row(raw, full, sheet_id=os.getenv("GOOGLE_SHEET_ID"), status=status)
    save_local_backup(raw, full)
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
    return client.audio.transcriptions.create(model=WHISPER_MODEL, file=audio_file).text.strip()


def chat_reply(user_text: str) -> str:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": (
                "Ты — голосовой помощник. Отвечай кратко, по делу, на том же языке, что и пользователь.")},
            {"role": "user", "content": user_text},
        ],
    )
    return resp.choices[0].message.content.strip()


def classify(text: str) -> str:
    """Возвращает: 'note' | 'question' | 'action'."""
    low = text.lower().strip()
    for key in CATEGORIES:
        if low.startswith(key):
            return "note"
    if low.startswith(("запиши", "сохрани", "note:")):
        return "note"
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": (
                "Определи тип команды пользователя. Ответь ОДНИМ словом:\n"
                "NOTE — если это просто заметка/идея/напоминание/то, что надо сохранить в дневник\n"
                "QUESTION — если это вопрос, на который надо просто ответить\n"
                "ACTION — если это реальное действие на компьютере (создать/удалить/переименовать папку или файл, "
                "запустить программу/скрипт, настроить что-то, скачать, и т.п. НЕ связанное с заметкой)\n"
                "Если сомневаешься — ACTION.")},
            {"role": "user", "content": text},
        ],
    )
    return resp.choices[0].message.content.strip().lower()


def summarize_task(text: str) -> str:
    """Краткое описание того, что бот понял — для подтверждения."""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": (
                "Пользователь дал задачу. Кратко (1-2 предложения) опиши, что ты понял и что сделаешь. "
                "Без лишних слов, на том же языке.")},
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
        "👋 Я бот-почтальон в Google Таблицу «Hermes Inbox».\n\n"
        "• Голосовое/текст — расшифрую.\n"
        "• Начни с <b>идея/таск/купить/журнал</b> — сохраню заметку.\n"
        "• Реальное действие (создать папку и т.п.) — спрошу подтверждение 🔘.\n"
        "• Просто вопрос — отвечу.\n"
        "Hermes дома выполнит задачи из таблицы.",
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
    ok = inbox_write(text, clean, cat or "📝 Заметка")
    await update.message.reply_text(
        ("✅ Записал: " if ok else "⚠️ Таблица недоступна, локально: ") + f"{cat or '📝 Заметка'} | {clean}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    await update.message.reply_text("🎤 Слушаю…")
    voice = await update.message.voice.get_file()
    audio_bytes = await voice.download_as_bytearray()
    try:
        text = transcribe(bytes(audio_bytes))
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось расшифровать: {e}")
        return
    if not text:
        await update.message.reply_text("🤔 Не услышал речи.")
        return
    context.user_data["last_text"] = text
    await process(update, text, raw=text)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return
    text = update.message.text
    context.user_data["last_text"] = text
    await process(update, text, raw=text)


async def process(update: Update, text: str, raw: str):
    kind = classify(text)
    log.info("Классификация: %s | %s", kind, text[:50])

    if kind == "note":
        clean = text.split(":", 1)[-1].strip() if ":" in text else text
        clean = clean.replace("запиши", "", 1).replace("сохрани", "", 1).strip()
        cat, body = detect_category(clean)
        ok = inbox_write(raw, body, cat or "📝 Заметка")
        await update.message.reply_text(
            ("✅ Записал в таблицу: " if ok else "⚠️ Локально: ") + f"{cat or '📝 Заметка'} | {body}")
        return

    if kind == "question":
        try:
            await update.message.reply_text(chat_reply(text))
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return

    # ACTION — подтверждение
    try:
        summary = summarize_task(text)
    except Exception:
        summary = text
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, сделай", callback_data=f"yes|{raw}"),
         InlineKeyboardButton("❌ Нет", callback_data="no")],
    ])
    await update.message.reply_text(
        f"🔘 Я понял так:\n<b>{summary}</b>\n\nСделать это?",
        parse_mode="HTML", reply_markup=keyboard,
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "no":
        await query.edit_message_text("❌ Отменено. Ничего не записал.")
        return
    if query.data.startswith("yes|"):
        raw = query.data[4:]
        ok = inbox_write(raw, raw, "⚙️ Действие", status="confirm")
        if ok:
            await query.edit_message_text(
                "✅ Записал как подтверждённую задачу. Hermes выполнит при включении компа.")
        else:
            await query.edit_message_text("⚠️ Таблица недоступна — сохранил локально.")


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Бот запущен v3 (с подтверждением).")
    app.run_polling()


if __name__ == "__main__":
    main()
