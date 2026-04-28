import requests
import os
import json
import logging
from datetime import datetime

# --- CONFIGURAZIONE LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURAZIONE CHIAVI ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GH_TOKEN = os.environ.get("MY_GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")
FILE_MEMORIA = "data/memoria.json"
ICONE = {"steam": "🎮", "epic-games-store": "🔥", "gog": "🟣", "ubisoft": "🌀"}

def invia_telegram(testo, bottoni=None):
    if not testo: return
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": testo, 
        "parse_mode": "Markdown", 
        "disable_web_page_preview": True
    }
    if bottoni:
        payload["reply_markup"] = {"inline_keyboard": bottoni}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        logging.error(f"Errore invio Telegram: {e}")

def sincronizza_presi(memoria):
    if not GH_TOKEN: return memoria
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    url_issues = f"https://api.github.com/repos/{REPO}/issues?state=open"
    try:
        issues = requests.get(url_issues, headers=headers).json()
        for issue in issues:
            titolo_issue = issue.get("title", "")
            if titolo_issue.startswith("PRESO:"):
                id_gioco = titolo_issue.replace("PRESO:", "").strip()
                if id_gioco in memoria:
                    memoria[id_gioco]["stato"] = "preso"
                    num = issue["number"]
                    requests.patch(f"https://api.github.com/repos/{REPO}/issues/{num}", 
                                   headers=headers, json={"state": "closed"})
                    logging.info(f"Gioco {id_gioco} segnato come PRESO via GitHub Issues.")
    except Exception as e:
        logging.error(f"Errore sincronizzazione: {e}")
    return memoria

# --- CORE ---
os.makedirs(os.path.dirname(FILE_MEMORIA), exist_ok=True)
if os.path.exists(FILE_MEMORIA):
    with open(FILE_MEMORIA, "r") as f: memoria = json.load(f)
else: memoria = {}

# 1. Vediamo se hai segnato qualcosa come preso su GitHub
memoria = sincronizza_presi(memoria)

logging.info("Recupero giochi dall'API...")
try:
    lista_items = requests.get("https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date").json()
except: lista_items = []

oggi = datetime.now()

for item in lista_items[:15]:
    id_item = str(item['id'])
    titolo = item['title']
    piattaforma = item['platforms'].lower()
    scadenza_str = item.get('end_date', 'N.D.')
    link_web = item['open_giveaway_url']
    tipo = item.get('type', 'Game')

    # Filtro Scadenza
    if scadenza_str != 'N.D.':
        try:
            if oggi > datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S"): continue
        except: pass

    # Se l'hai già preso, sparisce dal bot
    if memoria.get(id_item, {}).get("stato") == "preso":
        continue

    icona = "💻"
    for k, v in ICONE.items():
        if k in piattaforma: icona = v; break

    # --- LOGICA DLC ---
    if tipo != "Game":
        gioco_base_ipotetico = titolo.split(":")[0].split("-")[0].strip()
        possiede_base = False
        for m_id, m_data in memoria.items():
            if gioco_base_ipotetico.lower() in m_data.get('titolo', '').lower() and m_data.get('stato') == 'preso':
                possiede_base = True
                break
        
        if not possiede_base:
            # Se è un DLC e non hai il base, mandiamo un messaggio singolo di avviso
            testo_dlc = f"➕ *DLC DISPONIBILE*\n\n{titolo}\n\n⚠️ _Nota: Richiede il gioco base '{gioco_base_ipotetico}' che non risulta nella tua libreria._"
            # Per ora usiamo ancora il link Issue finché non facciamo Google Script
            link_ho_base = f"https://github.com/{REPO}/issues/new?title=PRESO:{id_item}&body=Ho+il+base+per+{titolo}"
            bottoni_dlc = [
                [{"text": "🚀 Vai allo Store", "url": link_web}],
                [{"text": "✅ Ho il gioco base (Segna)", "url": link_ho_base}]
            ]
            invia_telegram(testo_dlc, bottoni_dlc)
            # Salviamo comunque in memoria per non rimandarlo come "nuovo"
            if id_item not in memoria:
                memoria[id_item] = {"stato": "inviato", "titolo": titolo}
            continue

    # --- LOGICA GIOCHI NORMALI ---
    link_preso = f"https://github.com/{REPO}/issues/new?title=PRESO:{id_item}&body=Ho+preso+{titolo}"
    bottoni = [
        [{"text": "🚀 Vai allo Store", "url": link_web}],
        [{"text": "✅ Segna come preso", "url": link_preso}]
    ]

    if id_item not in memoria:
        testo = f"{icona} *NUOVO GIOCO*\n\n{titolo}\n⏰ Scade: {scadenza_str}"
        invia_telegram(testo, bottoni)
        memoria[id_item] = {"stato": "inviato", "titolo": titolo}
    else:
        # Reminder (puoi decidere di raggrupparli o mandarli singoli)
        testo = f"⏳ *REMINDER*\nNon hai ancora preso: {titolo}"
        invia_telegram(testo, bottoni)

# Salvataggio finale
with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
