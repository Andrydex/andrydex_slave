import requests
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health

def run_cheapshark_worker(memoria):
    try:
        # L'API magica: upperPrice=0 prende tutti i giochi gratis in quel momento!
        url = "https://www.cheapshark.com/api/1.0/deals?upperPrice=0"
        risposta = requests.get(url, timeout=10).json()

        for gioco in risposta[:10]: # Prendiamo i primi 10 per sicurezza
            titolo = gioco.get('title')
            deal_id = gioco.get('dealID')
            
            # Creiamo un ID unico usando il tuo mitico file hashing
            id_item = "cs_" + generate_hash(titolo)

            if memoria.get(id_item, {}).get("stato") in ["preso", "ignorato"]: 
                continue

            # CheapShark ci dà un link di reindirizzamento ufficiale allo store (Steam, Epic, ecc.)
            link = f"https://www.cheapshark.com/redirect?dealID={deal_id}"

            bottoni = [
                [{"text": "🚀 RISCATTA ORA", "url": link}],
                [{"text": "✅ Segna come preso", "callback_data": f"preso:{id_item}"}]
            ]

            if id_item not in memoria:
                invia_telegram(f"🦈 *SUPER DEAL (100% SCONTO)*\n\n{titolo}", bottoni)
                memoria[id_item] = {"stato": "inviato", "titolo": titolo}
                
        update_health("cheapshark_worker", "ok")
    except Exception as e:
        update_health("cheapshark_worker", f"error: {str(e)}")
    
    return memoria
