import requests
import os

print("🔍 Sto cercando gli ultimi giochi gratis per PC...")

# 1. IL CERCATORE
url_giochi = "https://www.gamerpower.com/api/giveaways?platform=pc"
risposta_giochi = requests.get(url_giochi)
lista_giochi = risposta_giochi.json()
ultimo_gioco = lista_giochi[0]

titolo = ultimo_gioco['title']
valore_originale = ultimo_gioco['worth']
piattaforma = ultimo_gioco['platforms']
link_gioco = ultimo_gioco['open_giveaway_url']

print(f"🎯 Trovato: {titolo} su {piattaforma}!")

# 2. IL POSTINO (Pesca i dati dalla cassaforte di GitHub in modo sicuro!)
TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

messaggio_telegram = f"🎮 NUOVO GIOCO GRATIS!\n\n🕹️ Titolo: {titolo}\n💰 Prima costava: {valore_originale}\n🏢 Piattaforma: {piattaforma}\n\n👉 Riscattalo qui:\n{link_gioco}"

url_telegram = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
dati = {"chat_id": CHAT_ID, "text": messaggio_telegram}

print("Sto inviando i dettagli al tuo telefono...")
requests.post(url_telegram, data=dati)

print("✅ Fatto! Controlla Telegram.")
