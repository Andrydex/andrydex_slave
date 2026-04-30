import requests
from datetime import datetime
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health

# 🔥 DIZIONARIO TRADUTTORE DEGLI STORE UFFICIALI
STORES = {
    "1": "Steam", "2": "GamersGate", "3": "GreenManGaming", "4": "Amazon",
    "7": "GOG", "8": "EA App", "11": "Humble Store", "24": "Epic Games", "25": "Fanatical"
}

def run_cheapshark_worker(memoria):
    try:
        url = "https://www.cheapshark.com/api/1.0/deals?upperPrice=0"
        risposta = requests.get(url, timeout=10).json()

        for gioco in risposta[:10]:
            titolo = gioco.get('title')
            deal_id = gioco.get('dealID')
            store_id = str(gioco.get('storeID'))
            
            # 🔥 TRADUCIAMO L'ID NELLO STORE REALE
            store_name = STORES.get(store_id, f"Store {store_id}")
            
            id_item = "cs_" + generate_hash(titolo)

            if memoria.get(id_item, {}).get("stato") in ["preso", "ignorato"]: 
                continue

            link = f"https://www.cheapshark.com/redirect?dealID={deal_id}"

            bottoni = [
                [{"text": "🚀 RISCATTA ORA", "url": link}],
                [{"text": "✅ Segna come preso", "callback_data": f"preso:{id_item}"}]
            ]

            if id_item not in memoria:
                invia_telegram(f"🦈 *SUPER DEAL (100% SCONTO)*\n\n{titolo}\n🏪 Store: `{store_name}`", bottoni)
                memoria[id_item] = {
                    "stato": "inviato", 
                    "titolo": titolo, 
                    "tipo": "cheapshark", 
                    "url": link, 
                    "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                }
            else:
                invia_telegram(f"⏳ *REMINDER DEAL*\nNon hai ancora preso: {titolo}\n🏪 Store: `{store_name}`", bottoni)
                
        update_health("cheapshark_worker", "ok")
    except Exception as e:
        update_health("cheapshark_worker", f"error: {str(e)}")
    
    return memoria
