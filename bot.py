import requests
import os
import json
from datetime import datetime

# --- CONFIGURAZIONE ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "memoria.json"
ESCLUDI_PIATTAFORME = ["amazon-prime", "twitch", "battlenet"]
ICONE = {"steam": "🎮 STEAM", "epic-games-store": "🔥 EPIC GAMES", "gog": "🟣 GOG"}

def invia_telegram(testo, link_bottone=None, reply_to_id=None, mostra_anteprima=True):
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": testo, "parse_mode": "Markdown"}
    if not mostra_anteprima:
        payload["disable_web_page_preview"] = True
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id
    if link_bottone:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": "🚀 RISCATTA ORA", "url": link_bottone}]]}
    
    try:
        r = requests.post(url, json=payload)
        return r.json()["result"]["message_id"] if r.json().get("ok") else None
    except:
        return None

# Caricamento memoria con protezione
if os.path.exists(FILE_MEMORIA):
    try:
        with open(FILE_MEMORIA, "r") as f:
            memoria = json.load(f)
    except:
        memoria = {}
else:
    memoria = {}

print("🔍 Ricerca giochi gratis...")
try:
    url_api = "https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date"
    lista_items = requests.get(url_api).json()
except:
    lista_items = []
    print("❌ Errore nel recupero dati dall'API")

oggi = datetime.now()

for item in lista_items[:10]:
    try:
        id_item = str(item['id'])
        titolo = item['title']
        piattaforma_raw = item['platforms'].lower()
        scadenza_str = item.get('end_date', 'N.D.')
        link = item['open_giveaway_url']
        
        # Filtro abbonamenti
        if any(p in piattaforma_raw for p in ESCLUDI_PIATTAFORME):
            continue

        # Controllo scadenza
        if scadenza_str != 'N.D.':
            try:
                if oggi > datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S"):
                    continue
            except: pass

        icona = "💻 PC"
        for chiave, t in ICONE.items():
            if chiave in piattaforma_raw:
                icona = t
                break

        if id_item not in memoria:
            testo = f"{icona}\n✨ *GIOCO GRATUITO*\n\n📝 *Titolo:* {titolo}\n⏰ *Scadenza:* {scadenza_str}"
            msg_id = invia_telegram(testo, link_bottone=link, mostra_anteprima=True)
            memoria[id_item] = {"stato": "inviato", "message_id": msg_id}
        else:
            # Reminder giornaliero
            id_msg_orig = memoria[id_item].get("message_id")
            reminder = f"⏳ *PROMO ANCORA ATTIVA*\nNon dimenticare *{titolo}*!"
            invia_telegram(reminder, link_bottone=link, reply_to_id=id_msg_orig, mostra_anteprima=False)
            
    except Exception as e:
        print(f"⚠️ Salto un gioco per errore: {e}")
        continue

# Salvataggio finale
with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
