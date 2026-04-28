import requests
import os
import json
import logging
from datetime import datetime

# --- CONFIGURAZIONE LOGGING PROFESSIONALE ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- CONFIGURAZIONE ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "data/memoria.json" # Sposteremo la memoria nella cartella data/
ESCLUDI_PIATTAFORME = ["amazon-prime", "twitch", "battlenet"]
ICONE = {"steam": "🎮", "epic-games-store": "🔥", "gog": "🟣", "ubisoft": "🌀"}

def invia_telegram(testo):
    if not testo: return
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": testo, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload)
        logging.info("Messaggio Telegram inviato con successo.")
    except Exception as e:
        logging.error(f"Errore nell'invio a Telegram: {e}")

# --- CREAZIONE CARTELLA DATA (se non esiste) ---
os.makedirs(os.path.dirname(FILE_MEMORIA), exist_ok=True)

# --- CARICAMENTO MEMORIA ---
if os.path.exists(FILE_MEMORIA):
    try:
        with open(FILE_MEMORIA, "r") as f:
            memoria = json.load(f)
            logging.info(f"Memoria caricata: {len(memoria)} elementi trovati.")
    except Exception as e: 
        memoria = {}
        logging.error(f"Errore lettura memoria (verrà ricreata): {e}")
else: 
    memoria = {}
    logging.info("Nessun file memoria trovato. Partenza da zero.")

logging.info("Inizio interrogazione API GamerPower...")
try:
    lista_items = requests.get("https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date", timeout=10).json()
    logging.info(f"API ha risposto con {len(lista_items)} elementi.")
except Exception as e: 
    lista_items = []
    logging.error(f"Impossibile collegarsi all'API GamerPower: {e}")

oggi = datetime.now()
nuovi_giochi = []
reminder_giochi = []

for item in lista_items[:15]:
    try:
        id_item = str(item['id'])
        titolo = item['title']
        piattaforma_raw = item['platforms'].lower()
        scadenza_str = item.get('end_date', 'N.D.')
        link = item['open_giveaway_url']

        if any(p in piattaforma_raw for p in ESCLUDI_PIATTAFORME): continue

        if scadenza_str != 'N.D.':
            try:
                if oggi > datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S"): continue
            except: pass

        icona = "💻"
        for chiave, ico in ICONE.items():
            if chiave in piattaforma_raw:
                icona = ico
                break

        riga = f"{icona} [{titolo}]({link}) (Scade: {scadenza_str})"

        if id_item not in memoria:
            nuovi_giochi.append(riga)
            memoria[id_item] = {"stato": "inviato", "titolo": titolo}
            logging.info(f"Nuovo gioco individuato: {titolo}")
        else:
            reminder_giochi.append(riga)
    except Exception as e:
        logging.warning(f"Errore durante l'elaborazione di un gioco: {e}")
        continue

# --- INVIO DEI MESSAGGI ---
if nuovi_giochi:
    logging.info(f"Invio di {len(nuovi_giochi)} nuovi giochi a Telegram.")
    invia_telegram("🎁 *NUOVI GIOCHI DISPONIBILI*\n\n" + "\n".join(nuovi_giochi))

if reminder_giochi:
    logging.info(f"Invio di {len(reminder_giochi)} reminder a Telegram.")
    invia_telegram("⏳ *PROMO ANCORA ATTIVE*\n\n" + "\n".join(reminder_giochi))

# --- SALVATAGGIO ---
try:
    with open(FILE_MEMORIA, "w") as f:
        json.dump(memoria, f, indent=4)
    logging.info("Memoria aggiornata e salvata su disco.")
except Exception as e:
    logging.error(f"Impossibile salvare la memoria su disco: {e}")
