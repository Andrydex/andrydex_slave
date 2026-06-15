import requests
from datetime import datetime
from telegram_sender import invia_telegram
from health_check import update_health

def is_scaduto_game(end_date_str):
    if not end_date_str or end_date_str in ("N/A", "N.D."):
        return False
    try:
        # GamerPower usa il formato: "2026-01-08 23:59:00"
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
        return end_date < datetime.now()
    except:
        return False

def run_gaming_worker(memoria):
    try:
        lista_items = requests.get("https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date", timeout=10).json()

        for item in lista_items[:15]:
            if item.get('status', '').lower() != 'active':
                continue
            id_item, titolo, link = str(item['id']), item['title'], item['open_giveaway_url']
            tipo = item.get('type', 'Game')
            piattaforma = item.get('platforms', 'PC/Store Vari')
            scadenza = item.get('end_date', 'N.D.')

            # 🛡️ FILTRO GIOCHI SCADUTI
            if is_scaduto_game(scadenza):
                memoria[id_item] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                continue

            if memoria.get(id_item, {}).get("stato") in ["preso", "ignorato"]: continue

            # LOGICA DLC
            if tipo != "Game":
                nome_base = titolo.split(":")[0].split("-")[0].strip()
                if not memoria.get(f"base_{nome_base.lower()}"):
                    testo = f"➕ *DLC DISPONIBILE*\n\n{titolo}\n🏪 Store: `{piattaforma}`\n⚠️ Richiede il base: `{nome_base}`\n⏳ Scadenza: `{scadenza}`"
                    bottoni = [
                        [{"text": "🚀 Store", "url": link}],
                        [{"text": "✅ Ho il base", "callback_data": f"ho_base:{nome_base}:{id_item}"}],
                        [{"text": "❌ Non ho il base", "callback_data": f"no_base:{id_item}"}]
                    ]
                    invia_telegram(testo, bottoni)
                    if id_item not in memoria: 
                        memoria[id_item] = {
                            "stato": "inviato", "titolo": titolo, "tipo": "dlc", "url": link, 
                            "scadenza": scadenza, "store": piattaforma,
                            "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                        }
                    continue

            # GIOCHI NORMALI
            bottoni = [
                [{"text": "🚀 RISCATTA ORA", "url": link}],
                [{"text": "✅ Segna come preso", "callback_data": f"preso:{id_item}"},
                 {"text": "❌ Ignora", "callback_data": f"ignora:{id_item}"}]
            ]
            if id_item not in memoria:
                bottoni_reminder = [
                    [{"text": "🚀 RISCATTA ORA", "url": link}],
                    [{"text": "✅ Segna come preso", "callback_data": f"preso:{id_item}"},
                     {"text": "❌ Ignora", "callback_data": f"ignora:{id_item}"}]
                ]
                invia_telegram(f"⏳ *REMINDER*\nNon hai ancora preso: {titolo}\n🏪 Store: `{piattaforma}`", bottoni_reminder)
                memoria[id_item] = {
                    "stato": "inviato", "titolo": titolo, "tipo": "gioco", "url": link, 
                    "scadenza": scadenza, "store": piattaforma,
                    "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                }
            else:
                invia_telegram(f"⏳ *REMINDER*\nNon hai ancora preso: {titolo}\n🏪 Store: `{piattaforma}`", bottoni)

        update_health("gaming_worker", "ok")
    except Exception as e:
        update_health("gaming_worker", f"error: {str(e)}")
    return memoria
