import requests
import os
import json

# --- CONFIGURAZIONE ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "memoria.json"

def invia_telegram(testo):
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": testo})

# 1. Carica la memoria (se il file non esiste, crea una lista vuota)
if os.path.exists(FILE_MEMORIA):
    with open(FILE_MEMORIA, "r") as f:
        memoria = json.load(f)
else:
    memoria = {}

print("🔍 Controllo nuovi giochi...")
url_giochi = "https://www.gamerpower.com/api/giveaways?platform=pc"
lista_giochi = requests.get(url_giochi).json()

# Prendiamo solo i primi 3 giochi più recenti per non intasare
for gioco in lista_giochi[:3]:
    id_gioco = str(gioco['id'])
    titolo = gioco['title']
    scadenza = gioco.get('end_date', 'N.D.')
    link = gioco['open_giveaway_url']

    # 2. Logica della memoria
    if id_gioco not in memoria:
        # GIOCO MAI VISTO
        messaggio = f"🎮 NUOVO GIOCO GRATIS!\n\n🕹️ {titolo}\n⏰ Scade il: {scadenza}\n👉 {link}"
        invia_telegram(messaggio)
        memoria[id_gioco] = {"stato": "inviato", "titolo": titolo}
        print(f"✅ Nuovo gioco segnalato: {titolo}")
    
    elif memoria[id_gioco]["stato"] == "inviato":
        # GIOCO GIÀ VISTO (Manda solo un breve reminder)
        messaggio = f"⏳ REMINDER: Non dimenticare di riscattare '{titolo}'! Scade a breve."
        invia_telegram(messaggio)
        print(f"ℹ️ Reminder inviato per: {titolo}")

# 3. Salva la memoria aggiornata nel file locale
with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
