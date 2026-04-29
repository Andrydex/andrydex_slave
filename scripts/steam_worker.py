import requests
from bs4 import BeautifulSoup
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health

URL = "https://store.steampowered.com/search/?maxprice=free"

def run_steam_worker(memoria):
    try:
        response = requests.get(URL, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        results = soup.select("a.search_result_row")

        for item in results[:5]:
            title_elem = item.select_one(".title")
            if not title_elem: continue

            titolo = title_elem.text.strip()
            link = item["href"]
            id_item = "steam_" + generate_hash(titolo) # Creiamo un ID unico usando l'hashing!

            if memoria.get(id_item, {}).get("stato") in ["preso", "ignorato"]: continue

            bottoni = [
                [{"text": "🚀 RISCATTA ORA", "url": link}],
                [{"text": "✅ Segna come preso", "callback_data": f"preso:{id_item}"}]
            ]

            if id_item not in memoria:
                invia_telegram(f"🚂 *NUOVO SU STEAM*\n\n{titolo}", bottoni)
                memoria[id_item] = {"stato": "inviato", "titolo": titolo}

        update_health("steam_worker", "ok")
    except Exception as e:
        update_health("steam_worker", f"error: {str(e)}")
    return memoria
