import requests
from bs4 import BeautifulSoup
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health
from datetime import datetime

# Sorgenti aggiornate
URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "tutti i dipartimenti", "biagi", "finance"]
EXCLUDE = ["giurisprudenza", "area giuridica", "diritto"]
# 💰 Radar per soldi e viaggi
FUNDING = ["grant", "scholarship", "funding", "travel", "borse", "studio", "viaggio", "finanziamento", "reimbursement"]

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            
            for link_tag in soup.find_all('a', href=True):
                testo = link_tag.text.strip().lower()
                href = link_tag['href']
                
                if not testo or len(testo) < 5: continue

                is_interessante = any(p in testo for p in INCLUDE)
                is_giurisprudenza = any(p in testo for p in EXCLUDE)
                # Controllo se ci sono soldi in ballo
                ha_fondi = any(p in testo for p in FUNDING)

                if is_interessante and not (is_giurisprudenza and "economia" not in testo):
                    if not href.startswith("http"):
                        href = "https://www.unimore.it" + href if "unimore" in url else href
                    
                    id_bando = "uni_" + generate_hash(href)

                    if id_bando not in memoria:
                        etichetta_fondi = "💰 **POSSIBILE FINANZIAMENTO / BORSA**\n" if ha_fondi else ""
                        
                        testo_messaggio = (
                            f"🎓 **AVVISO UNIVERSITÀ**\n\n"
                            f"{etichetta_fondi}"
                            f"📌 {link_tag.text.strip()}\n"
                            f"🏫 Fonte: `{nome_fonte}`\n\n"
                            f"✈️ _Verifica nella Dashboard se coprono le spese di viaggio._"
                        )
                        
                        bottoni = [
                            [{"text": "🌐 Leggi Dettagli", "url": href}],
                            [{"text": "📊 Dashboard", "url": "https://YOUR_USERNAME.github.io/andrydex_slave/"}]
                        ]
                        
                        invia_telegram(testo_messaggio, bottoni)
                        
                        memoria[id_bando] = {
                            "stato": "nuovo",
                            "titolo": link_tag.text.strip(),
                            "url": href,
                            "tipo": "universita",
                            "funding": ha_fondi,
                            "data_rilevazione": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
        
        update_health("unigreen_worker", "ok")
    except Exception as e:
        update_health("unigreen_worker", f"error: {str(e)}")
    
    return memoria
