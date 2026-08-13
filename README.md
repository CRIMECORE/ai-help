# Obsidian Voice Bot

Telegram-бот, который принимает **голосовые сообщения**, расшифровывает их в текст
и сохраняет как заметки в формате **Obsidian** (`.md` с YAML frontmatter).

## Возможности
- 🎤 Голосовые → расшифровка (Whisper) → заметка в Obsidian
- 💬 Текстовые сообщения → умный ответ (LLM) или сохранение заметки
- 📝 Команды: `/note <текст>`, `/last`, `/start`
- 🔒 Опционально: ограничение по Telegram ID

## Развёртывание на bot-host.ru
1. Залей этот репозиторий на GitHub.
2. На https://bothost.ru/create-bot.php укажи:
   - Платформа: **Telegram**
   - Git URL: ссылка на этот репозиторий
   - Ветка: `main`
   - Bot Token: токен от @BotFather
3. В панели bot-host.ru → Environment Variables задай:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY` (и при необходимости `OPENAI_BASE_URL`, `CHAT_MODEL`)
   - `NOTES_DIR=./notes`
   - `ALLOWED_USER_ID` (твой Telegram ID, узнать у @userinfobot)
4. Бот соберётся и запустится 24/7.

## Синхронизация заметок домой (в твой Obsidian Vault)
Папку `NOTES_DIR` на сервере синхронизируй с локальной папкой Obsidian через:
- **Syncthing** (рекомендуется, бесплатно, без гитхаба), или
- **git** (делай commit/push на сервере, pull дома), или
- **Obsidian Sync** (платно).

Тогда заметки, продиктованные на прогулке, появятся в твоём вольте дома.

## Локальный запуск (для теста)
```bash
pip install -r requirements.txt
cp .env.example .env   # и заполни значения
python main.py
```
