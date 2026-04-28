import requests
import os
import json
from datetime import datetime

# --- CONFIGURAZIONE ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "memoria.json"
ESCLUDI_PIATTAFORME = ["amazon-prime", "twitch", "battlenet"]
ICONE = {"steam": "🎮", "epic-games-store": "🔥", "gog": "🟣", "ubisoft": "🌀"}

def invia_telegram(testo):
    if not testo: return
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": testo, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True # Niente anteprime giganti per risparmiare spazio
    }
    requests.post(url, json=payload)

# Caricamento memoria
if os.path.exists(FILE_MEMORIA):
    try:
        with open(FILE_MEMORIA, "r") as f:
            memoria = json.load(f)
    except: memoria = {}
else: memoria = {}

print("🔍 Analisi giochi in corso...")
try:
    lista_items = requests.get("https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date").json()
except: lista_items = []

oggi = datetime.now()
nuovi_giochi = []
reminder_giochi = []

for item in lista_items[:15]: # Controlliamo più giochi per sicurezza
    id_item = str(item['id'])
    titolo = item['title']
    piattaforma_raw = item['platforms'].lower()
    scadenza_str = item.get('end_date', 'N.D.')
    link = item['open_giveaway_url']

    if any(p in piattaforma_raw for p in ESCLUDI_PIATTAFORME): continue

    # Controllo scadenza
    if scadenza_str != 'N.D.':
        try:
            if oggi > datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S"): continue
        except: pass

    # Icona
    icona = "💻"
    for chiave, ico in ICONE.items():
        if chiave in piattaforma_raw:
            icona = ico
            break

    # Formattazione riga: [Titolo](Link) - Scadenza
    riga = f"{icona} [{titolo}]({link}) (Scade: {scadenza_str})"

    if id_item not in memoria:
        nuovi_giochi.append(riga)
        memoria[id_item] = {"stato": "inviato", "titolo": titolo}
    else:
        # Se vuoi il tasto "Preso", in futuro qui controlleremo se lo stato è "preso"
        reminder_giochi.append(riga)

# --- INVIO DEI MESSAGGI RAGGRUPPATI ---
if nuovi_giochi:
    testo_nuovi = "🎁 *NUOVI GIOCHI DISPONIBILI*\n\n" + "\n".join(nuovi_giochi)
    invia_telegram(testo_nuovi)

if reminder_giochi:
    testo_reminder = "⏳ *PROMO ANCORA ATTIVE*\n\n" + "\n".join(reminder_giochi)
    invia_telegram(testo_reminder)

# Salvataggio
with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
