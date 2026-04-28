import requests
import os
import json
from datetime import datetime

# --- CONFIGURAZIONE ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "memoria.json"

# Piattaforme che NON vogliamo (perché richiedono abbonamenti)
ESCLUDI_PIATTAFORME = ["amazon-prime", "twitch", "battlenet"]

# Icone per rendere il bot più bello
ICONE = {
    "steam": "🎮 STEAM",
    "epic-games-store": "🔥 EPIC GAMES",
    "gog": "🟣 GOG",
    "ubisoft": "🌀 UBISOFT",
    "origin": "🟠 EA APP",
    "drm-free": "🆓 DRM-FREE",
    "itchio": "🕹️ ITCH.IO"
}

def invia_telegram(testo, link_bottone=None, reply_to_id=None, mostra_anteprima=True):
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": testo, "parse_mode": "Markdown"}
    
    if not mostra_anteprima:
        payload["disable_web_page_preview"] = True
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id
    if link_bottone:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🚀 RISCATTA ORA", "url": link_bottone}]]
        }
        
    risposta = requests.post(url, json=payload).json()
    return risposta["result"]["message_id"] if risposta.get("ok") else None

# --- CARICAMENTO MEMORIA ---
if os.path.exists(FILE_MEMORIA):
    with open(FILE_MEMORIA, "r") as f:
        memoria = json.load(f)
else:
    memoria = {}

print("🔍 Ricerca regali PC in corso (Senza abbonamenti)...")
# Chiediamo all'API tutti i giveaway per PC ordinati per valore/data
url_api = "https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date"
lista_items = requests.get(url_api).json()

oggi = datetime.now()

# Analizziamo i primi 10 risultati per non perdere nulla
for item in lista_items[:10]:
    id_item = str(item['id'])
    titolo = item['title']
    piattaforma_raw = item['platforms'].lower()
    scadenza_str = item.get('end_date', 'N.D.')
    link = item['open_giveaway_url']
    tipo = item.get('type', 'Game')
    valore = item.get('worth', 'Gratis')

    # 1. FILTRO ABBONAMENTI: Salta se la piattaforma è nella nostra lista nera
    if any(p in piattaforma_raw for p in ESCLUDI_PIATTAFORME):
        continue

    # 2. FILTRO SCADENZA
    if scadenza_str != 'N.D.':
        try:
            if oggi > datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S"):
                continue
        except: pass

    # 3. ICONA PIATTAFORMA
    icona = "💻 PC"
    for chiave, testo in ICONE.items():
        if chiave in piattaforma_raw:
            icona = testo
            break

    etichetta_tipo = "🎁 GIOCO" if tipo == "Game" else "➕ DLC/ADD-ON"

    # --- INVIO MESSAGGI ---
    if id_item not in memoria:
        testo = (f"{icona}\n"
                 f"✨ *{etichetta_tipo} GRATUITO*\n\n"
                 f"📝 *Titolo:* {titolo}\n"
                 f"💰 *Valore:* {valore}\n"
                 f"⏰ *Scadenza:* {scadenza_str}")
        
        msg_id = invia_telegram(testo, link_bottone=link, mostra_anteprima=True)
        memoria[id_item] = {"stato": "inviato", "titolo": titolo, "message_id": msg_id}
        print(f"✅ Inviato: {titolo}")
        
    elif memoria[id_item]["stato"] == "inviato":
        id_msg_orig = memoria[id_item].get("message_id")
        if id_msg_orig:
            reminder = f"⏳ *PROMO ANCORA ATTIVA*\nNon hai ancora preso *{titolo}*?\nScade il: {scadenza_str}"
            invia_telegram(reminder, link_bottone=link, reply_to_id=id_msg_orig, mostra_anteprima=False)

# --- SALVATAGGIO ---
with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
