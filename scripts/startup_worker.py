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

URLS_STARTUP = {
    "ART-ER (Emilia Romagna)": "https://www.art-er.it/bandi/",
    "Regione Molise (Bandi)": "https://www.regione.molise.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/1",
    "Invitalia (Nazionali)": "https://www.invitalia.it/cosa-facciamo/creiamo-nuove-aziende"
}

# 🛠️ FILTRO AMPLIATO: Ora cerca queste parole anche dentro gli URL
KEYWORDS_STARTUP = ["bando", "startup", "agevolazione", "contributo", "finanziamento", "imprese", "innovazione", "incentiv", "smart", "fondo", "misura", "nuove-aziende"]

def carica_tutti_i_pdf():
    testo = "--- PROFILO FOUNDER E IDEA DI STARTUP ---\n"
    cartella = "context"
    if not os.path.exists(cartella): return testo
    
    for filename in os.listdir(cartella):
        if filename.lower().endswith(".pdf"):
            try:
                with open(os.path.join(cartella, filename), "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages[:10]:
                        testo += page.extract_text() + "\n"
            except Exception as e:
                logging.warning(f"Errore lettura {filename}: {e}")
    return testo[:20000]

CONTESTO_STARTUP = carica_tutti_i_pdf()

def estrai_testo_startup(url):
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
            if ".pdf" in href.lower() or any(k in a_tag.text.lower() for k in ["bando", "avviso", "scarica", "allegato"]):
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
    if not testo or not client: return {"scadenza":"N.D.", "voto":"0"}
    try:
        prompt = (
            f"DATI DEL PROGETTO E DEL SOLO FOUNDER:\n{CONTESTO_STARTUP}\n\n"
            f"Analizza questo testo. REGOLA FONDAMENTALE: Se il testo è solo una pagina informativa generica o NON c'è un modo chiaro per candidarsi (nessuna scadenza definita o 'sportello aperto' specificato), DEVI assegnare rigorosamente 'voto': 1. Valuta la compatibilità (da 1 a 10) SOLO se è un vero bando/agevolazione attivo per le startup.\n"
            f"Rispondi SOLO con JSON valido, nessun backtick o testo extra:\n"
            f'{{"scadenza":"DD/MM/YYYY oppure Sportello","ente":"...","requisiti":"...","tipo_fondo":"Fondo perduto / Finanziamento","voto":7}}\n'
            f"TESTO BANDO: {testo[:30000]}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw = response.text.strip().strip('`').replace('json', '', 1).strip()
        return json.loads(raw)
    except: return {"scadenza": "Errore"}

def run_startup_worker(memoria):
    try:
        for nome_fonte, url in URLS_STARTUP.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            
            for link_tag in soup.find_all('a', href=True):
                href = link_tag['href'].lower()
                testo_l = link_tag.text.strip().lower()
                
                # 🛡️ FILTRO: Controlla parole chiave SIA nel testo che nell'URL
                if not any(k in testo_l for k in KEYWORDS_STARTUP) and not any(k in href for k in KEYWORDS_STARTUP): 
                    continue
                    
                # 🛡️ FILTRO: Escludi roba inutile
                if any(x in href for x in ["facebook", "twitter", "instagram", "linkedin", "youtube"]): 
                    continue
                
                real_url = link_tag['href'] if link_tag['href'].startswith("http") else urljoin(url, link_tag['href'])
                
                # Salta se è la pagina stessa
                if real_url == url: continue

                id_bando = "start_" + generate_hash(real_url)

                if memoria.get(id_bando, {}).get("stato") in ["ignorato", "partecipo"]: continue
                
                if id_bando not in memoria:
                    logging.info(f"🚀 Analizzo bando startup: {testo_l or real_url}")
                    testo_completo = estrai_testo_startup(real_url)
                    time.sleep(5) # Rate limit Gemini
                    
                    dati_ai = analizza_startup_con_ai(testo_completo)
                    scadenza = str(dati_ai.get("scadenza", "N.D."))
                    
                    if scadenza == "Errore": continue
                    
                    try:
                        score = int(''.join(filter(str.isdigit, str(dati_ai.get("voto", "5")))))
                        if score < 5:
                            memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                            continue
                    except: score = 5

                    ente = dati_ai.get('ente', 'N.D.')
                    tipo_fondo = dati_ai.get('tipo_fondo', 'N.D.')
                    requisiti = dati_ai.get('requisiti', 'N.D.')

                    msg = f"🚀 **BANDO STARTUP ({score}/10)**\n\n📌 *{link_tag.text.strip() or 'Vedi link'}*\n🏢 **Ente:** {ente}\n⏳ **Scadenza:** `{scadenza}`\n💰 **Tipo:** {tipo_fondo}\n📝 **Requisiti:** _{requisiti}_"
                    invia_telegram(msg, [
                        [{"text": "🌐 Vai al Bando", "url": real_url}],
                        [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                         {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                        [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
                    ])
                    
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip() or "Bando Startup", "url": real_url, "tipo": "startup",
                        "scadenza": scadenza, "ente": ente, "requisiti": requisiti, "fondo": tipo_fondo,
                        "voto": score, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("startup_worker", "ok")
    except Exception as e:
        logging.error(f"Errore startup_worker: {e}")
        update_health("startup_worker", f"error: {str(e)}")
    
    return memoria
