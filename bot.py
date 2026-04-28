import requests
import os
import json
from datetime import datetime

# --- CONFIGURAZIONE E CHIAVI ---
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_MEMORIA = "memoria.json"

def invia_telegram(testo, reply_to_id=None, mostra_anteprima=True):
    """
    Invia un messaggio a Telegram. 
    L'interruttore 'mostra_anteprima' decide se far vedere l'immagine del link.
    """
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": testo
    }
    
    # Se NON vogliamo l'anteprima, la disattiviamo
    if not mostra_anteprima:
        payload["disable_web_page_preview"] = True
        
    # Se c'è un ID, risponde a quel messaggio
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id
        
    risposta = requests.post(url, json=payload).json()
    
    if risposta.get("ok"):
        return risposta["result"]["message_id"]
    return None

# --- GESTIONE MEMORIA LOCALE ---
if os.path.exists(FILE_MEMORIA):
    with open(FILE_MEMORIA, "r") as f:
        memoria = json.load(f)
else:
    memoria = {}

print("🔍 Inizio analisi dei giochi gratuiti e calcolo scadenze...")
url_giochi = "https://www.gamerpower.com/api/giveaways?platform=pc"
lista_giochi = requests.get(url_giochi).json()

oggi = datetime.now()

for gioco in lista_giochi[:5]: 
    id_gioco = str(gioco['id'])
    titolo = gioco['title']
    scadenza_str = gioco.get('end_date', 'N.D.')
    link = gioco['open_giveaway_url']
    
    # CONTROLLO SCADENZA
    if scadenza_str != 'N.D.':
        try:
            data_scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M:%S")
            if oggi > data_scadenza:
                print(f"⏩ Salto '{titolo}' perché è scaduto il {scadenza_str}.")
                continue 
        except ValueError:
            print(f"⚠️ Formato data non riconosciuto per '{titolo}', procedo comunque.")

    # LOGICA DEI MESSAGGI E RISPOSTE
    if id_gioco not in memoria:
        # GIOCO NUOVO: Mostriamo l'anteprima del link
        messaggio = f"🎮 NUOVO GIOCO GRATIS!\n\n🕹️ {titolo}\n⏰ Scade il: {scadenza_str}\n👉 {link}"
        
        msg_id = invia_telegram(messaggio, mostra_anteprima=True)
        
        memoria[id_gioco] = {
            "stato": "inviato", 
            "titolo": titolo,
            "message_id": msg_id 
        }
        print(f"✅ Nuovo gioco segnalato e salvato in memoria: {titolo}")
        
    elif memoria[id_gioco]["stato"] == "inviato":
        # REMINDER: Niente anteprima e risponde al messaggio originale
        id_messaggio_originale = memoria[id_gioco].get("message_id")
        
        if id_messaggio_originale:
            messaggio_reminder = f"⏳ REMINDER SCADENZA\nRicordati di riscattare questo gioco entro il: {scadenza_str}"
            
            invia_telegram(messaggio_reminder, reply_to_id=id_messaggio_originale, mostra_anteprima=False)
            print(f"ℹ️ Reminder inviato per: {titolo}")

# --- SALVATAGGIO DEI DATI ---
with open(FILE_MEMORIA, "w") as f:
    json.dump(memoria, f, indent=4)
print("💾 Memoria sincronizzata e salvata.")
