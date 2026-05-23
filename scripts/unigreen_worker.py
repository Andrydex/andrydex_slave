import requests
import os
import io
import json
import time
import pypdf
import logging
from google import genai
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health
from datetime import datetime

# Configurazione Log per capire cosa fa GitHub Actions
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

BLACKLIST_DOMAINS = ["facebook", "twitter", "instagram", "linkedin", "youtube", "pica.cineca.it", "tel.unimore"]
BLACKLIST_TEXT = ["contatti", "privacy", "cookie", "newsletter", "magazine", "amministrazione trasparente", "intranet", "sicurezza"]
# Ho ri-aggiunto "bando" e "avviso" per non farci sfuggire niente!
INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "biagi", "finance", "erasmus", "student", "mobility", "bando", "avviso", "selezione"]

PROFILO_UTENTE = (
    "Studente magistrale DCI (Direzione e consulenza d'impresa, curricula di imprenditorialità) - 1° anno magistrale, Dipartimento Biagi, Unimore. "
    "Cerca: Mobilità internazionale, BIP, Erasmus, borse di studio aperte a studenti magistrali iscritti. "
    "Escludi: bandi per soli triennalisti, dottorati (richiedono laurea magistrale già conseguita), "
    "Giurisprudenza, Medicina, Scienze della Vita, Scienze Infermieristiche, concorsi per personale docente/TAB. "
    "REGOLA DIPARTIMENTI (PRIORITARIA): Se il bando elenca dipartimenti o corsi ammessi e DCI/Economia/Biagi/Management NON compare tra essi, assegna OBBLIGATORIAMENTE voto 1 e spiega nel campo 'requisiti' quali dipartimenti sono invece ammessi. "
    "Voto alto (8-10) solo se esplicitamente aperto a magistrali iscritti di Economia o area affine."
)

def carica_contesto_pdf():
    contesto = ""
    for filename in ["context/CV_03_2026.pdf", "context/Profilo_7_aprile_2026.pdf"]:
        if os.path.exists(filename):
            try:
                with open(filename, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages:
                        contesto += page.extract_text() + "\n"
            except Exception as e:
                logging.warning(f"Errore lettura {filename}: {e}")
    return contesto[:10000] # Limite di sicurezza per i token

CONTESTO_AGGIUNTIVO = carica_contesto_pdf()

def is_scaduto(scadenza_str):
    from datetime import datetime
    import re
    if not scadenza_str or scadenza_str in ("N.D.", "Errore"): return False
    
    # Traduzione mesi italiani per evitare crash
    mesi = {"gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04", "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08", "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12"}
    s = scadenza_str.lower().strip()
    for m, num in mesi.items(): s = s.replace(m, num)
    
    # Cerca una data nel testo
    match = re.search(r'(\d{1,2})[\s\/\-](\d{1,2})[\s\/\-](\d{4})', s)
    if match:
        g, m, a = match.groups()
        try: return datetime(int(a), int(m), int(g)) < datetime.now()
        except: pass
    return False

def estrai_testo_da_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=25, headers=headers)
        if response.status_code != 200: return ""
        
        # 1. Se il link è GIÀ un PDF diretto (comportamento classico)
        if url.lower().endswith(".pdf") or "application/pdf" in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                testo = ""
                pagine = list(range(min(15, num_pages)))
                if num_pages > 15: pagine.extend(range(max(15, num_pages - 15), num_pages))
                for i in sorted(list(set(pagine))):
                    testo += reader.pages[i].extract_text() + "\n"
                return testo[:50000]
                
        # 2. Se è una pagina HTML (Pagina Informativa) -> DEEP SCRAPING
        soup = BeautifulSoup(response.text, "html.parser")
        testo_pagina = soup.get_text(separator=' ', strip=True)
        
        testo_allegati = "\n\n--- TESTO ALLEGATI TROVATI NELLA PAGINA ---\n"
        trovati = False
        
        # Cerchiamo solo nel <main> o nel body per evitare link spam nel footer
        main_content = soup.find('main') or soup.find('body') or soup
        
        for a_tag in main_content.find_all('a', href=True):
            href = a_tag['href']
            testo_link = a_tag.text.lower()
            
            # Cerchiamo link a PDF o bottoni con scritto "bando", "avviso", "allegato"
            if ".pdf" in href.lower() or any(k in testo_link for k in ["bando", "avviso", "allegato", "scarica"]):
                pdf_url = href if href.startswith("http") else urljoin(url, href)
                
                # Evita loop infiniti se il link punta alla pagina stessa
                if pdf_url == url: continue 
                
                try:
                    pdf_resp = requests.get(pdf_url, timeout=15, headers=headers)
                    if "application/pdf" in pdf_resp.headers.get('Content-Type', '') or pdf_url.lower().endswith(".pdf"):
                        trovati = True
                        with io.BytesIO(pdf_resp.content) as f:
                            reader = pypdf.PdfReader(f)
                            # Leggiamo le prime 20 pagine di ogni allegato trovato
                            for page in reader.pages[:20]: 
                                testo_allegati += page.extract_text() + "\n"
                except Exception as e:
                    logging.warning(f"Impossibile leggere allegato {pdf_url}: {e}")
        
        testo_finale = testo_pagina
        if trovati:
            testo_finale += testo_allegati
            
        return testo_finale[:50000] # Tagliamo sempre a 50k per non far impazzire Gemini
        
    except Exception as e:
        logging.warning(f"Errore estrazione da {url}: {e}")
        return ""

def analizza_con_ai(testo):
    if not testo or not client: return {"scadenza":"N.D.", "voto":"0"}
    try:
        prompt = (
            f"PROFILO DI BASE: {PROFILO_UTENTE}\n"
            f"DETTAGLI CV/PROFILO (dal PDF): {CONTESTO_AGGIUNTIVO}\n"
            f"Analizza questo testo. "
            f"REGOLA 1 (PAGINA GENERICA): Se il testo è solo una pagina informativa, un articolo, o NON ha una scadenza definita per candidarsi, assegna 'voto': 1 e 'scadenza': 'N.D.'. "
            f"REGOLA 2 (DIPARTIMENTI): Se il bando specifica dipartimenti o corsi ammessi e DCI/Economia/Biagi non è incluso, assegna 'voto': 1 e scrivi quali dipartimenti sono ammessi nel campo 'requisiti'. "
            f"REGOLA 3 (DOTTORATI): Se il bando richiede laurea già conseguita o è per dottorandi, assegna 'voto': 1. "
            f"Valuta 6-10 SOLO se il bando è concretamente accessibile a uno studente magistrale iscritto al 1° anno di DCI.\n"
            f"Rispondi SOLO con JSON valido, nessun testo extra, nessun backtick:\n"
            f'{{"scadenza":"DD/MM/YYYY oppure esattamente N.D. (nessun altro testo permesso)","luogo":"...","durata":"...","ente":"...","argomenti":"...","requisiti":"...","voto":7}}\n'
            f"IMPORTANTE: il campo 'scadenza' deve contenere SOLO una data in formato DD/MM/YYYY oppure esattamente la stringa N.D. — mai testo descrittivo.\n"
            f"TESTO: {testo[:40000]}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw = response.text.strip().strip('`').replace('json', '', 1).strip()
        return json.loads(raw)
    except Exception as e:
        logging.warning(f"Errore AI Gemini: {e}")
        return {"scadenza": "Errore"}

def run_unigreen_worker(memoria):
    try:
        queue = []
        visti = set()
        
        # 1. Raccogliamo i link dalle pagine principali (Livello 1)
        for nome_fonte, url in URLS.items():
            try:
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, "html.parser")
                main_c = soup.find('main') or soup
                for link_tag in main_c.find_all('a', href=True):
                    href = link_tag['href']
                    testo_l = link_tag.text.strip().lower()
                    if any(x in href.lower() for x in BLACKLIST_DOMAINS) or any(x in testo_l for x in BLACKLIST_TEXT): continue
                    if not any(x in testo_l for x in INCLUDE): continue
                    real_url = href if href.startswith("http") else urljoin(url, href)
                    if real_url not in visti:
                        visti.add(real_url)
                        queue.append({"titolo": link_tag.text.strip(), "url": real_url, "depth": 1})
            except Exception as e:
                logging.warning(f"Errore radice {url}: {e}")

        # 2. Processiamo la coda scavando dove serve
        while queue:
            item = queue.pop(0)
            titolo_link, real_url, depth = item["titolo"], item["url"], item["depth"]

            id_bando = "uni_" + generate_hash(real_url)
            stato_attuale = memoria.get(id_bando, {}).get("stato")
            if stato_attuale in ["ignorato", "partecipo"]: continue
            
            if id_bando in memoria and stato_attuale == "nuovo":
                dati = memoria[id_bando]
                msg_r = f"⏳ *REMINDER BANDO ({dati.get('voto','?')}/10)*\n\n📌 *{dati.get('titolo','')}*\n⏳ **Scadenza:** `{dati.get('scadenza','N.D.')}`\n📝 **Requisiti:** _{dati.get('requisiti','N.D.')}_"
                invia_telegram(msg_r, [
                    [{"text": "🌐 Apri Documento", "url": dati.get("url", "")}],
                    [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                     {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                    [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
                ])
                continue
                
            if id_bando not in memoria:
                logging.info(f"🕵️ Analizzo (Livello {depth}): {titolo_link[:30]}...")
                testo_pdf = estrai_testo_da_url(real_url)
                time.sleep(10) 
                
                dati_ai = analizza_con_ai(testo_pdf)
                scadenza = normalizza_scadenza(str(dati_ai.get("scadenza", "N.D.")))
                if scadenza == "Errore": continue 
                
                try: score = int(''.join(filter(str.isdigit, str(dati_ai.get("voto", "5")))))
                except: score = 5

                # 🛑 SE SCARTATO o scadenza N.D. (Pagina generica) -> ESPLORA I LINK INTERNI
                if score < 5 or scadenza == "N.D.":
                    memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                    if depth < 2:  # Scava fino a Livello 2
                        logging.info(f"🔄 Pagina generica, estraggo sotto-link da: {real_url}")
                        try:
                            sub_resp = requests.get(real_url, timeout=15)
                            sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                            sub_main = sub_soup.find('main') or sub_soup
                            for sub_a in sub_main.find_all('a', href=True):
                                s_href = sub_a['href']
                                s_testo = sub_a.text.strip().lower()
                                if any(x in s_href.lower() for x in BLACKLIST_DOMAINS) or any(x in s_testo for x in BLACKLIST_TEXT): continue
                                if not any(x in s_testo for x in INCLUDE): continue
                                next_url = s_href if s_href.startswith("http") else urljoin(real_url, s_href)
                                if next_url not in visti:
                                    visti.add(next_url)
                                    queue.append({"titolo": sub_a.text.strip(), "url": next_url, "depth": depth + 1})
                        except: pass
                    continue

                if is_scaduto(scadenza):
                    memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                    continue

                    def normalizza_scadenza(s):
                        import re
                        if not s: return "N.D."
                        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', s.strip()):
                            return s.strip()
                        return "N.D."
                
                # ✅ BANDO TROVATO
                msg = f"🎓 **BANDO ({score}/10)**\n\n📌 *{titolo_link}*\n🏢 **Ente:** {dati_ai.get('ente','N.D.')}\n⏳ **Scadenza:** `{scadenza}`\n📝 **Requisiti:** _{dati_ai.get('requisiti','N.D.')}_"
                invia_telegram(msg, [
                    [{"text": "🌐 Apri Documento", "url": real_url}],
                    [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                     {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                    [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
                ])
                
                memoria[id_bando] = {
                    "stato": "nuovo", "titolo": titolo_link, "url": real_url, "tipo": "universita",
                    "scadenza": scadenza, "luogo": dati_ai.get("luogo", "N.D."), 
                    "durata": dati_ai.get("durata", "N.D."), "ente": dati_ai.get("ente", "N.D."),
                    "argomenti": dati_ai.get("argomenti", "N.D."), "requisiti": dati_ai.get("requisiti", "N.D."),
                    "voto": score, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                }
        update_health("unigreen_worker", "ok")
    except Exception as e: 
        logging.error(f"Errore critico in unigreen_worker: {e}")
        update_health("unigreen_worker", f"error: {str(e)}")
    
    return memoria
