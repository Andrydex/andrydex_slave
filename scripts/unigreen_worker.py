import requests
import os
import google.generativeai as genai
from bs4 import BeautifulSoup
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health
from datetime import datetime

# Configuriamo l'AI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # Modello perfetto per estrazione rapida e precisa
    model = genai.GenerativeModel('gemini-1.5-flash')

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "tutti i dipartimenti", "biagi", "finance"]
EXCLUDE = ["giurisprudenza", "area giuridica", "diritto"]
FUNDING = ["grant", "scholarship", "funding", "travel", "borse", "studio", "viaggio", "finanziamento", "reimbursement"]

def analizza_bando_con_ai(url):
    if not GEMINI_KEY: return "AI Disattivata", "AI Disattivata"
    try:
        # 1. Apriamo la pagina del bando specifico
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Prendiamo solo i primi 4000 caratteri (sono più che sufficienti per trovare le info principali)
        testo_pagina = soup.get_text(separator=' ', strip=True)[:4000]
        
        # 2. Chiediamo a Gemini di analizzarlo
        prompt = """Sei un assistente universitario. Leggi questo estratto di bando e trova:
        1. Scadenza per presentare la domanda.
        2. Periodo di svolgimento (o destinazione se presente).
        Rispondi SOLO in questo formato esatto:
        Scadenza: [inserisci data o 'Non specificata']
        Periodo/Destinazione: [inserisci periodo o luogo o 'Non specificato']
        
        Testo del bando: """ + testo_pagina

        risposta = model.generate_content(prompt)
        testo_ai = risposta.text.strip().split('\n')
        
        scadenza = testo_ai[0].replace("Scadenza:", "").replace("**", "").strip() if len(testo_ai) > 0 else "Non specificata"
        periodo = testo_ai[1].replace("Periodo/Destinazione:", "").replace("**", "").strip() if len(testo_ai) > 1 else "Non specificato"
        
        return scadenza, periodo
    except Exception as e:
        return "Da verificare", "Da verificare"

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
                ha_fondi = any(p in testo for p in FUNDING)

                if is_interessante and not (is_giurisprudenza and "economia" not in testo):
                    if not href.startswith("http"):
                        href = "https://www.unimore.it" + href if "unimore" in url else href
                    
                    id_bando = "uni_" + generate_hash(href)

                    if id_bando not in memoria:
                        
                        # ✨ LA MAGIA: Chiediamo a Gemini di leggere il bando!
                        scadenza, periodo = analizza_bando_con_ai(href)
                        
                        etichetta_fondi = "💰 **POSSIBILE FINANZIAMENTO**\n" if ha_fondi else ""
                        
                        testo_messaggio = (
                            f"🎓 **AVVISO UNIVERSITÀ**\n\n"
                            f"{etichetta_fondi}"
                            f"📌 *{link_tag.text.strip()}*\n\n"
                            f"🏫 **Fonte:** `{nome_fonte}`\n"
                            f"⏳ **Scadenza:** `{scadenza}`\n"
                            f"🌍 **Svolgimento:** `{periodo}`\n"
                        )
                        
                        bottoni = [
                            [{"text": "🌐 Apri Bando", "url": href}],
                            [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
                        ]
                        
                        invia_telegram(testo_messaggio, bottoni)
                        
                        memoria[id_bando] = {
                            "stato": "nuovo",
                            "titolo": link_tag.text.strip(),
                            "url": href,
                            "tipo": "universita",
                            "funding": ha_fondi,
                            "scadenza": scadenza,
                            "periodo": periodo,
                            "data_rilevazione": datetime.now().strftime("%d/%m/%Y %H:%M") # <-- DATA SISTEMATA
                        }
        
        update_health("unigreen_worker", "ok")
    except Exception as e:
        update_health("unigreen_worker", f"error: {str(e)}")
    
    return memoria
