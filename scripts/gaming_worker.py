import requests, os, json, logging
from datetime import datetime

# 📥 IMPORTIAMO GLI ATTREZZI DAGLI ALTRI FILE
from telegram_sender import invia_telegram
from health_check import update_health

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GH_TOKEN = os.environ.get("MY_GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")
FILE_MEMORIA = "data/memoria.json"

def sincronizza_presi(memoria):
    if not GH_TOKEN: return memoria
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        issues = requests.get(f"https://api.github.com/repos/{REPO}/issues?state=open", headers=headers).json()
        for issue in issues:
            titolo_i = issue.get("title", "")
            num = issue['number']
            if titolo_i.startswith("PRESO:"):
                id_g = titolo_i.replace("PRESO:", "").strip()
                if id_g in memoria: memoria[id_g]["stato"] = "preso"
            elif titolo_i.startswith("HO_BASE:"):
                nome_base = titolo_i.replace("HO_BASE:", "").strip().lower()
                memoria[f"base_{nome_base}"] = {"stato": "preso", "titolo": nome_base}
            elif titolo_i.startswith("NO_BASE:"):
                id_g = titolo_i.replace("NO_BASE:", "").strip()
                memoria[id_g] = {"stato": "ignorato"}
            
            # Chiude l'issue in ogni caso
            requests.patch(f"https://api.github.com/repos/{REPO}/issues/{num}", headers=headers, json={"state": "closed"})
    except: pass
    return memoria

os.makedirs(os.path.dirname(FILE_MEMORIA), exist_ok=True)
memoria = json.load(open(FILE_MEMORIA, "r")) if os.path.exists(FILE_MEMORIA) else {}
memoria = sincronizza_presi(memoria)

try:
    lista_items = requests.get("https://www.gamerpower.com/api/giveaways?platform=pc&sort-by=date").json()
    oggi = datetime.now()

    for item in lista_items[:15]:
        id_item, titolo, link = str(item['id']), item['title'], item['open_giveaway_url']
        tipo = item.get('type', 'Game')

        if memoria.get(id_item, {}).get("stato") in ["preso", "ignorato"]: continue

        # LOGICA DLC
        if tipo != "Game":
            nome_base = titolo.split(":")[0].split("-")[0].strip()
            if not memoria.get(f"base_{nome_base.lower()}"):
                testo = f"➕ *DLC DISPONIBILE*\n\n{titolo}\n⚠️ Richiede il base: `{nome_base}`"
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
            invia_telegram(f"🎮 *NUOVO GIOCO*\n\n{titolo}", bottoni)
            memoria[id_item] = {"stato": "inviato", "titolo": titolo}
        else:
            invia_telegram(f"⏳ *REMINDER*\nNon hai ancora preso: {titolo}", bottoni)

    json.dump(memoria, open(FILE_MEMORIA, "w"), indent=4)
    update_health("gaming_worker", "ok")

except Exception as e:
    update_health("gaming_worker", f"error: {str(e)}")
    raise
