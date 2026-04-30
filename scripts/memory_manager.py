import json
import os
from datetime import datetime, timedelta

MEMORIA_PATH = 'data/memoria.json'

def load_memory():
    if os.path.exists(MEMORIA_PATH):
        try:
            with open(MEMORIA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except: return {}
    return {}

def save_memory(memoria):
    limite_giochi = datetime.now() - timedelta(days=30)
    limite_bandi = datetime.now() - timedelta(days=60)
    
    nuova_memoria = {}
    for k, v in memoria.items():
        # 🛡️ FIX: Controlliamo che v sia un dizionario
        if not isinstance(v, dict): continue 
        
        data_rif = v.get("data_rilevazione", "01/01/2000")
        try:
            data_dt = datetime.strptime(data_rif.split()[0], "%d/%m/%Y")
        except:
            data_dt = datetime.now()

        if v.get("tipo") == "universita":
            if data_dt > limite_bandi: nuova_memoria[k] = v
        else:
            if data_dt > limite_giochi: nuova_memoria[k] = v
    
    with open(MEMORIA_PATH, 'w', encoding='utf-8') as f:
        json.dump(nuova_memoria, f, indent=4, ensure_ascii=False)

def sincronizza_presi(memoria):
    """Legge gli aggiornamenti di Telegram e sincronizza lo stato nella memoria."""
    import os, requests
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    if not token: return memoria

    def sincronizza_presi(memoria):
    """Legge gli aggiornamenti di Telegram e sincronizza lo stato nella memoria."""
    import os, requests
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    if not token: return memoria

    try:
        # Legge l'offset salvato per non riprocessare vecchi messaggi
        offset = memoria.get("__telegram_offset__", 0)
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=5"
        updates = requests.get(url, timeout=10).json().get("result", [])

        for update in updates:
            offset = update["update_id"] + 1
            cb = update.get("callback_query")
            if not cb: continue
            if str(cb.get("message", {}).get("chat", {}).get("id", "")) != chat_id: continue

            data = cb.get("data", "")

            if data.startswith("preso:"):
                item_id = data.split(":", 1)[1]
                if item_id in memoria:
                    memoria[item_id]["stato"] = "preso"

            elif data.startswith("no_base:"):
                item_id = data.split(":", 1)[1]
                if item_id in memoria:
                    memoria[item_id]["stato"] = "ignorato"

            elif data.startswith("partecipo:"):
                item_id = data.split(":", 1)[1]
                if item_id in memoria:
                    memoria[item_id]["stato"] = "partecipo"

            elif data.startswith("ignora_bando:"):
                item_id = data.split(":", 1)[1]
                if item_id in memoria:
                    memoria[item_id]["stato"] = "ignorato"

            # Risponde a Telegram per togliere il "loading" sul bottone
            requests.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={"callback_query_id": cb["id"], "text": "✅ Salvato!"},
                timeout=5
            )

        memoria["__telegram_offset__"] = offset

    except Exception as e:
        import logging
        logging.warning(f"Errore sincronizza_presi: {e}")

    return memoria
