import requests
import os
import json
from datetime import datetime

TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "memoria.json"

# Abbiamo aggiunto 'link_bottone' per creare il pulsante sotto al messaggio
def invia_telegram(testo, link_bottone=None, reply_to_id=None, mostra_anteprima=True):
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo
    }
    
    if not mostra_anteprima:
        payload["disable_web_page_preview"] = True
        
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id

    # Se passiamo un link, Telegram crea il bottone cliccabile
    if link_bottone:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🎮 Vai al Gioco", "url": link_bottone}]]
        }
        
    risposta = requests.post(url, json=payload).json()
    
    if risposta.get("ok"):
        return risposta["result"]["message_id"]
    return None

# --- GESTIONE MEMORIA ---
if os.path.exists(FILE_MEMORIA):
    with open(FILE_MEMORIA, "r") as f:
        memoria = json.load(f)
else:
    memoria = {}

print("🔍 Controllo giochi in corso...")
url_giochi = "https://www.gamerpower.com/api/giveaways?platform=pc"
lista_giochi = requests.get(url_giochi).json()
oggi = datetime.now()

for gioco in lista_giochi[:5]: 
    id_gioco = str(gioco['id'])
    titolo = gioco['title']
    scadenza_str = gioco.get('end_date', 'N.D.')
    link = gioco['open_giveaway_url']
    tipo = gioco.get('type', 'Game') # Capisce se è un Game o un DLC/Loot
    
    # Rinomina per renderlo più chiaro nel messaggio
    etichetta_tipo = "📦 DLC / LOOT" if tipo != "Game" else "🏆 GIOCO COMPLETO"

    # CONTROLLO SCADENZA
    if scadenza_str != 'N.D.':
        try:
            data_scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S")
            if oggi > data_scadenza:
                continue 
        except ValueError:
            pass

    # LOGICA MESSAGGI
    if id_gioco not in memoria:
        messaggio = f"*{etichetta_tipo} GRATIS!*\n\n🕹️ {titolo}\n⏰ Scade il: {scadenza_str}"
        # Ora passiamo il link al bottone, non nel testo!
        msg_id = invia_telegram(messaggio, link_bottone=link, mostra_anteprima=True)
        
        memoria[id_gioco] = {"stato": "inviato", "titolo": titolo, "message_id": msg_id}
        
    elif memoria[id_gioco]["stato"] == "inviato":
        id_msg_orig = memoria[id_gioco].get("message_id")
        if id_msg_orig:
            messaggio_reminder = f"⏳ REMINDER SCADENZA: {titolo}\nScade il: {scadenza_str}"
            # Il reminder ha un pulsante per riscattarlo subito senza scorrere su
            invia_telegram(messaggio_reminder, link_bottone=link, reply_to_id=id_msg_orig, mostra_anteprima=False)

with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
