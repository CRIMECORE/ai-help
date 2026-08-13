"""
sheets_writer.py — пишет задачи в Google Таблицу "Hermes Inbox".
Это общий "почтовый ящик" между ТГ-ботом и Hermes (агентом на компе).

Авторизация (на bot-host):
  GOOGLE_SHEET_ID            - ID таблицы (из URL)
  GOOGLE_CREDENTIALS_JSON    - JSON сервисного аккаунта (рекомендуется для сервера)
  ИЛИ GOOGLE_CREDENTIALS_FILE - путь к файлу сервисного аккаунта
"""

import os
import json
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except Exception:
    SHEETS_AVAILABLE = False

_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]


def _client():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
    else:
        path = os.getenv("GOOGLE_CREDENTIALS_FILE")
        if not path:
            return None
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
    creds = Credentials.from_service_account_info(info, scopes=_SCOPE)
    return gspread.authorize(creds)


def add_inbox_row(raw, task, sheet_id=None, status="new"):
    """Добавляет строку в лист Inbox. Возвращает True/False."""
    sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id or not SHEETS_AVAILABLE:
        return False
    try:
        gc = _client()
        if not gc:
            return False
        ws = gc.open_by_key(sheet_id).worksheet("Inbox")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws.append_row([ts, raw, task, status, ""])
        return True
    except Exception as e:
        print(f"[sheets_writer] ошибка записи: {e}")
        return False
