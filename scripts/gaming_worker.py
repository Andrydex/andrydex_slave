import requests
from datetime import datetime
from telegram_sender import invia_telegram
from health_check import update_health

def run_gaming_worker(memoria):
    try:
        lista_items = requests.get("https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date", timeout=10).json()

        for item in lista_items[:15]:
            id_item, titolo, link = str(item['id']), item['title'], item['open_giveaway_url']
            tipo = item.get('type', 'Game')
            
            # 🔥 ESTRAIAMO LO STORE/PIATTAFORMA
            piattaforma = item.get('platforms', 'PC/Store Vari')

            if memoria.get(id_item, {}).get("stato") in ["preso", "ignorato"]: continue

            # LOGICA DLC
            if tipo != "Game":
                nome_base = titolo.split(":")[0].split("-")[0].strip()
                if not memoria.get(f"base_{nome_base.lower()}"):
                    testo = f"➕ *DLC DISPONIBILE*\n\n{titolo}\n🏪 Store: `{piattaforma}`\n⚠️ Richiede il base: `{nome_base}`"
                    bottoni = [
                        [{"text": "🚀 Store", "url": link}],
                        [{"text": "✅ Ho il base", "callback_data": f"ho_base:{nome_base}"}],
                        [{"text": "❌ Non ho il base", "callback_data": f"no_base:{id_item}"}]
                    ]
                    invia_telegram(testo, bottoni)
                    if id_item not in memoria: memoria[id_item] = {"stato": "inviato"}
                    continue

            # GIOCHI NORMALI
            bottoni = [
                [{"text": "🚀 RISCATTA ORA", "url": link}],
                [{"text": "✅ Segna come preso", "callback_data": f"preso:{id_item}"}]
            ]
            if id_item not in memoria:
                invia_telegram(f"🎮 *NUOVO GIOCO*\n\n{titolo}\n🏪 Store: `{piattaforma}`", bottoni)
                memoria[id_item] = {"stato": "inviato", "titolo": titolo}
            else:
                invia_telegram(f"⏳ *REMINDER*\nNon hai ancora preso: {titolo}\n🏪 Store: `{piattaforma}`", bottoni)

        update_health("gaming_worker", "ok")
    except Exception as e:
        update_health("gaming_worker", f"error: {str(e)}")
    return memoria
