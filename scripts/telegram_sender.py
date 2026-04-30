import requests
import os
import logging

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def invia_telegram(messaggio, bottoni=None):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.error("Credenziali Telegram mancanti!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": messaggio,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    if bottoni:
        payload["reply_markup"] = {"inline_keyboard": bottoni}

    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            logging.warning(f"Telegram error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logging.error(f"Errore invio Telegram: {e}")
