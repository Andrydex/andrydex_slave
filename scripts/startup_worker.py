import requests
import os
import io
import json
import time
import pypdf
import logging
from datetime import datetime
from google import genai
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# 🎯 SITI DA MONITORARE (Puoi aggiungerne altri in futuro)
URLS_STARTUP = {
    "ART-ER (Emilia Romagna)": "https://www.art-er.it/bandi/",
    "Regione Molise (Bandi)": "https://www.regione.molise.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/1",
    "Invitalia (Nazionali)": "https://www.invitalia.it/cosa-facciamo/creiamo-nuove-aziende"
}

KEYWORDS_STARTUP = ["bando", "startup", "agevolazione", "contributo", "finanziamento", "imprese", "innovazione"]

def carica_tutti_i_pdf():
    """Legge dinamicamente tutti i PDF nella cartella context/"""
    testo = "--- PROFILO FOUNDER E IDEA DI STARTUP ---\n"
    cartella = "context"
    if not os.path.exists(cartella): return testo
    
    for filename in os.listdir(cartella):
        if filename.lower().endswith(".pdf"):
            try:
                with open(os.path.join(cartella, filename), "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages[:10]: # Limite 10 pagine a PDF per non esplodere
                        testo += page.extract_text() + "\n"
            except Exception as e:
                logging.warning(f"Errore lettura {filename}: {e}")
    return testo[:20000]

CONTESTO_STARTUP = carica_tutti_i_pdf()

def estrai_testo_startup(url):
    """Esegue il Deep Scraping (HTML + eventuali PDF allegati)"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=25, headers=headers)
        if response.status_code != 200: return ""
        
        if url.lower().endswith(".pdf") or "application/pdf" in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                return "".join([p.extract_text() for p in pypdf.PdfReader(f).pages[:15]])[:50000]
                
        soup = BeautifulSoup(response.text, "html.parser")
        testo_pagina = soup.get_text(separator=' ', strip=True)
        testo_allegati = "\n--- ALLEGATI ---\n"
        trovati = False
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if ".pdf" in href.lower() or any(k in a_tag.text.lower() for k in ["bando", "avviso", "scarica"]):
                pdf_url = href if href.startswith("http") else urljoin(url, href)
                if pdf_url == url: continue
                try:
                    pdf_resp = requests.get(pdf_url, timeout=15, headers=headers)
                    if "application/pdf" in pdf_resp.headers.get('Content-Type', '') or pdf_url.lower().endswith(".pdf"):
                        trovati = True
                        with io.BytesIO(pdf_resp.content) as f:
                            testo_allegati += "".join([p.extract_text() for p in pypdf.PdfReader(f).pages[:10]])
                except: pass
        
        return (testo_pagina + (testo_allegati if trovati else ""))[:50000]
    except: return ""

def analizza_startup_con_ai(testo):
    if not testo or not client: return "N.D.", "N.D.", "N.D.", "N.D.", "0"
    try:
        prompt = (
            f"DATI DEL PROGETTO E DEL SOLO FOUNDER:\n{CONTESTO_STARTUP}\n\n"
            f"Analizza questo bando per imprese/startup. Valuta la compatibilità (da 1 a 10) per il progetto descritto, tenendo conto che il team è composto da un singolo fondatore.\n"
            f"Rispondi SOLO con JSON valido, nessun backtick o testo extra:\n"
            f'{{"scadenza":"DD/MM/YYYY","ente":"...","requisiti":"...","tipo_fondo":"Fondo perduto / Finanziamento","voto":7}}\n'
            f"TESTO BANDO: {testo[:30000]}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw = response.text.strip().strip('`').replace('json', '', 1).strip()
        d = json.loads(raw)
        return str(d.get("scadenza", "N.D.")), str(d.get("ente", "N.D.")), str(d.get("requisiti", "N.D.")), str(d.get("tipo_fondo", "N.D.")), str(d.get("voto", "0"))
    except: return "Errore", "Errore", "Errore", "Errore", "0"

def run_startup_worker(memoria):
    try:
        for nome_fonte, url in URLS_STARTUP.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            
            for link_tag in soup.find_all('a', href=True):
                testo_l = link_tag.text.strip().lower()
                if not any(k in testo_l for k in KEYWORDS_STARTUP): continue
                
                href = link_tag['href']
                real_url = href if href.startswith("http") else urljoin(url, href)
                id_bando = "start_" + generate_hash(real_url)

                if memoria.get(id_bando, {}).get("stato") in ["ignorato", "partecipo"]: continue
                
                if id_bando not in memoria:
                    logging.info(f"🚀 Analizzo bando startup: {testo_l}")
                    testo_completo = estrai_testo_startup(real_url)
                    time.sleep(5) # Rate limit Gemini
                    
                    scadenza, ente, requisiti, tipo_fondo, voto = analizza_startup_con_ai(testo_completo)
                    if scadenza == "Errore": continue
                    
                    try:
                        score = int(''.join(filter(str.isdigit, str(voto))))
                        if score < 5:
                            memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                            continue
                    except: score = 5

                    msg = f"🚀 **BANDO STARTUP ({score}/10)**\n\n📌 *{link_tag.text.strip()}*\n🏢 **Ente:** {ente}\n⏳ **Scadenza:** `{scadenza}`\n💰 **Tipo:** {tipo_fondo}\n📝 **Requisiti:** _{requisiti}_"
                    invia_telegram(msg, [
                        [{"text": "🌐 Vai al Bando", "url": real_url}],
                        [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                         {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}]
                    ])
                    
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip(), "url": real_url, "tipo": "startup",
                        "scadenza": scadenza, "ente": ente, "requisiti": requisiti, "fondo": tipo_fondo,
                        "voto": score, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("startup_worker", "ok")
    except Exception as e:
        logging.error(f"Errore startup_worker: {e}")
        update_health("startup_worker", f"error: {str(e)}")
    
    return memoria
