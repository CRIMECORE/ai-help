# Obsidian Voice Bot (ai-help)

Telegram-бот, который принимает **голосовые и текст**, расшифровывает их и пишет
задачи в **Google Таблицу «Hermes Inbox»** — общий «почтовый ящик» с агентом Hermes
на компе, который выполняет задачи и создаёт заметки в **Obsidian**.

## Что умеет
- 🎤 Голосовое → расшифровка (Whisper) → задача в таблицу
- 💬 Текст → умный ответ (LLM) / сохранение / действие
- 📝 Категории: `идея` / `таск` / `купить` / `журнал` / `напомни` → расклад по папкам
- ⚙️ **Реальное действие** (создать папку и т.п.) → бот шлёт подтверждение
  с кнопками **[Да] / [Нет]**. Только «Да» → пишет в таблицу (status=confirm).
  «Нет» → ничего не пишет и не делает.
- ❓ Просто вопрос → отвечает, ничего не пишет

## Переменные окружения (bot-host → Environment Variables)
| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен от @BotFather |
| `OPENAI_API_KEY` | ключ LLM/Whisper (OpenAI или OpenRouter) |
| `OPENAI_BASE_URL` | опц. база API (для OpenRouter и т.п.) |
| `CHAT_MODEL` | опц., `gpt-4o-mini` |
| `WHISPER_MODEL` | опц., `whisper-1` |
| `GOOGLE_SHEET_ID` | `1lmA-VtNqa0bk-sqcnJ1_eGBL44M19iWz1Rbeu-ZV07I` |
| `GOOGLE_CREDENTIALS_JSON` | **весь JSON сервисного аккаунта Google** (в кавычках) |
| `ALLOWED_USER_ID` | твой Telegram ID (узнать у @userinfobot) |
| `APPROVE_CHAT_ID` | куда слать подтверждения (= ALLOWED_USER_ID) |
| `NOTES_DIR` | опц., `./notes` (локальный резерв) |

### Как получить GOOGLE_CREDENTIALS_JSON
1. Google Cloud Console → IAM → Service Accounts → создать `hermes-bot`
2. Keys → Add Key → JSON → скачать
3. Поделиться таблицей с `client_email` из ключа (права Редактор)
4. Вставить весь JSON в переменную `GOOGLE_CREDENTIALS_JSON`

## Развёртывание на bot-host.ru
1. https://bothost.ru/create-bot.php → Telegram, Git URL = этот репозиторий, ветка `main`, Bot Token
2. В панели bot-host → Environment Variables (см. таблицу выше)
3. Бот соберётся и запустится 24/7

## Локальный запуск
```bash
pip install -r requirements.txt
cp .env.example .env   # заполнить значения
python main.py
```
(файл service_account.json в .gitignore — не попадёт на GitHub)
