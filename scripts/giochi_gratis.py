import requests
import os
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURAZIONE ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GH_TOKEN = os.environ.get("MY_GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY") # Preso in automatico da GitHub
FILE_MEMORIA = "data/memoria.json"
ICONE = {"steam": "🎮", "epic-games-store": "🔥", "gog": "🟣", "ubisoft": "🌀"}

for item in lista_items[:15]:
    # ... (estrazione dati)
    tipo = item.get('type', 'Game')
    titolo = item['title']
    
    # LOGICA DLC
    if tipo != "Game":
        # Cerchiamo di capire qual è il gioco base (spesso il titolo del DLC lo contiene)
        # Esempio: "The Sims 4: Luxury Stuff" -> Gioco base: "The Sims 4"
        gioco_base_ipotetico = titolo.split(":")[0].split("-")[0].strip()
        
        # Controlliamo in memoria se possiedi il gioco base
        possiede_base = False
        for id_m, dati_m in memoria.items():
            if gioco_base_ipotetico.lower() in dati_m.get('titolo', '').lower() and dati_m.get('stato') == 'preso':
                possiede_base = True
                break
        
        if not possiede_base:
            # Messaggio specifico per DLC senza gioco base
            testo = f"➕ *DLC DISPONIBILE*\n\n{titolo}\n\n⚠️ _Nota: Questo è un DLC. Non mi risulta che tu abbia il gioco base '{gioco_base_ipotetico}'._"
            bottoni = [
                [{"text": "🚀 Vai allo Store", "url": link_web}],
                [{"text": "✅ Ho il gioco base", "callback_data": f"ho_base:{id_item}"}], # Questo richiede il Webhook!
                [{"text": "❌ Non ho il base", "callback_data": f"no_base:{id_item}"}]
            ]
            invia_telegram(testo, bottoni)
            continue # Passa al prossimo

def invia_telegram(testo, bottoni=None):
    if not testo: return
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": testo, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if bottoni:
        payload["reply_markup"] = {"inline_keyboard": bottoni}
    requests.post(url, json=payload)

# --- LOGICA PER GESTIRE I "PRESI" TRAMITE GITHUB ISSUES ---
def sincronizza_presi(memoria):
    if not GH_TOKEN: return memoria
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    url_issues = f"https://api.github.com/repos/{REPO}/issues?state=open"
    
    try:
        issues = requests.get(url_issues, headers=headers).json()
        for issue in issues:
            titolo = issue.get("title", "")
            if titolo.startswith("PRESO:"):
                id_gioco = titolo.replace("PRESO:", "").strip()
                if id_gioco in memoria:
                    memoria[id_gioco]["stato"] = "preso"
                    logging.info(f"Gioco {id_gioco} segnato come PRESO.")
                    # Chiudiamo l'issue in automatico
                    num = issue["number"]
                    requests.patch(f"https://api.github.com/repos/{REPO}/issues/{num}", 
                                   headers=headers, json={"state": "closed"})
    except Exception as e:
        logging.error(f"Errore sincronizzazione Issues: {e}")
    return memoria

# --- CORE ---
os.makedirs(os.path.dirname(FILE_MEMORIA), exist_ok=True)
if os.path.exists(FILE_MEMORIA):
    with open(FILE_MEMORIA, "r") as f: memoria = json.load(f)
else: memoria = {}

# Sincronizziamo i click dell'utente prima di procedere
memoria = sincronizza_presi(memoria)

logging.info("Analisi API...")
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

    # Filtro Scadenza
    if scadenza_str != 'N.D.':
        try:
            if oggi > datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S"): continue
        except: pass

    # Se l'utente lo ha segnato come preso, lo ignoriamo per sempre
    if memoria.get(id_item, {}).get("stato") == "preso":
        continue

    icona = "💻"
    for k, v in ICONE.items():
        if k in piattaforma: icona = v; break

    # Creazione dei bottoni
    link_preso = f"https://github.com/{REPO}/issues/new?title=PRESO:{id_item}&body=Ho+preso+{titolo.replace(' ', '+')}"
    bottoni = [
        [{"text": "🚀 Vai allo Store", "url": link_web}],
        [{"text": "✅ Segna come preso", "url": link_preso}]
    ]

    if id_item not in memoria:
        testo = f"{icona} *NUOVO GIOCO*\n\n{titolo}\n⏰ Scade: {scadenza_str}"
        invia_telegram(testo, bottoni)
        memoria[id_item] = {"stato": "inviato", "titolo": titolo}
    else:
        # Reminder giornaliero se non è ancora "preso"
        testo = f"⏳ *REMINDER*\nNon hai ancora preso: {titolo}\nScade: {scadenza_str}"
        invia_telegram(testo, bottoni)

with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
