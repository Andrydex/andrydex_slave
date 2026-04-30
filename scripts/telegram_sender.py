import requests
import os
import logging

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def invia_telegram(testo, bottoni=None):
    if not testo:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    # Se ci sono bottoni, li aggiunge al messaggio
    if bottoni:
        payload["reply_markup"] = {"inline_keyboard": bottoni}

    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            logging.warning(f"Telegram error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logging.error(f"Errore invio Telegram: {e}")
