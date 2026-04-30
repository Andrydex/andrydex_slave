import requests
import os
import google.generativeai as genai
from bs4 import BeautifulSoup
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health
from datetime import datetime

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

# 🛑 BLACKLIST: Link da ignorare assolutamente
BLACKLIST_DOMAINS = ["facebook", "twitter", "instagram", "linkedin", "youtube", "radiofsc", "pica.cineca.it"]
BLACKLIST_TEXT = ["contatti", "privacy", "cookie", "newsletter", "magazine", "store", "governance", "social", "chi siamo", "facebook", "twitter", "amministrazione trasparente", "intranet", "sicurezza", "mappa", "feedback"]

INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "tutti i dipartimenti", "biagi", "finance", "student", "mobility", "erasmus", "mission"]

def analizza_bando_con_ai(url):
    if not GEMINI_KEY: return "N.D.", "N.D.", False, "0"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, timeout=15, headers=headers)
        if response.status_code != 200: return "Errore Pagina", "N.D.", False, "0"
        
        soup = BeautifulSoup(response.text, "html.parser")
        testo_pagina = soup.get_text(separator=' ', strip=True)[:5000]
        
        prompt = f"Analizza questo bando per uno studente di ECONOMIA. Estrai: 1. Scadenza (data o 'Scaduto'). 2. Periodo/Destinazione. 3. Borsa (SI/NO). 4. Compatibilità (1-10). Rispondi in 4 righe pulite.\nTesto: {testo_pagina}"
        
        risposta = model.generate_content(prompt).text.strip().split('\n')
        scadenza = risposta[0].split(":")[1].strip() if ":" in risposta[0] else "N.D."
        periodo = risposta[1].split(":")[1].strip() if ":" in risposta[1] else "N.D."
        borsa = "SI" in risposta[2].upper()
        voto = risposta[3].split(":")[1].strip() if ":" in risposta[3] else "5"
        
        return scadenza, periodo, borsa, voto
    except:
        return "Da verificare", "Da verificare", False, "5"

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 🎯 Cerchiamo solo nei blocchi di contenuto principale, non in tutta la pagina
            main_content = soup.find('main') or soup.find('article') or soup
            
            for link_tag in main_content.find_all('a', href=True):
                href = link_tag['href'].lower()
                testo = link_tag.text.strip().lower()
                
                # 🚫 FILTRO 1: Salta i domini vietati
                if any(social in href for social in BLACKLIST_DOMAINS): continue
                # 🚫 FILTRO 2: Salta i testi inutili
                if any(junk in testo for junk in BLACKLIST_TEXT): continue
                # 🚫 FILTRO 3: Deve esserci una delle parole chiave
                if not any(word in testo for word in INCLUDE): continue
                
                real_url = href if href.startswith("http") else ("https://www.unimore.it" + href if "unimore" in url else href)
                id_bando = "uni_" + generate_hash(real_url)

                if id_bando not in memoria:
                    print(f"Analizzando bando reale: {testo}")
                    scadenza, periodo, borsa, voto = analizza_bando_con_ai(real_url)
                    
                    if "scaduto" in scadenza.lower() or (voto.isdigit() and int(voto) < 4):
                        memoria[id_bando] = {"stato": "ignorato"}
                        continue

                    testo_m = f"🎓 **BANDO SELEZIONATO** ({voto}/10)\n\n📌 *{link_tag.text.strip()}*\n⏳ **Scadenza:** `{scadenza}`\n🌍 **Svolgimento:** `{periodo}`\n🏪 **Borsa:** {'✅ SI' if borsa else '❌ NO'}"
                    invia_telegram(testo_m, [[{"text": "🌐 Apri", "url": real_url}]])
                    
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip(), "url": real_url,
                        "tipo": "universita", "funding": borsa, "scadenza": scadenza,
                        "periodo": periodo, "voto": voto, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("unigreen_worker", "ok")
    except Exception as e:
        update_health("unigreen_worker", f"error: {str(e)}")
    return memoria
