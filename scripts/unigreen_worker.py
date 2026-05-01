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
    "Studente magistrale DCI (Direzione e consulenza d'impresa, curricula di imprenditorialietà) - 1° anno magistrale, Dipartimento Biagi, Unimore. "
    "Cerca: Mobilità internazionale, BIP, Erasmus, borse di studio aperte a studenti magistrali. "
    "Escludi: bandi per soli triennalisti, dottorati (richiedono laurea magistrale completata), "
    "corsi di laurea (già iscritto), Giurisprudenza, Medicina, concorsi per personale docente/TAB. "
    "Voto alto (8-10) solo se accessibile a magistrali iscritti, voto basso (1-4) se richiede titolo già conseguito o è per altri corsi."
)

def carica_contesto_pdf():
    contesto = ""
    for filename in ["CV_03_2026.pdf", "Profilo_7_aprile_2026.pdf"]:
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
    """Restituisce True se la scadenza è già passata."""
    from datetime import datetime
    if not scadenza_str or scadenza_str in ("N.D.", "Errore"): return False
    formati = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%B %d, %Y"]
    for fmt in formati:
        try:
            return datetime.strptime(scadenza_str.strip(), fmt) < datetime.now()
        except: continue
    return False

def estrai_testo_da_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=25, headers=headers)
        if response.status_code != 200: return ""
        
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
                
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator=' ', strip=True)[:50000]
    except Exception as e:
        logging.warning(f"Errore estrazione PDF/HTML da {url}: {e}")
        return ""

def analizza_con_ai(testo):
    if not testo or not client: return "N.D.", "N.D.", "N.D.", False, "0"
    try:
        prompt = (
            f"PROFILO DI BASE: {PROFILO_UTENTE}\n"
            f"DETTAGLI CV/PROFILO (dal PDF): {CONTESTO_AGGIUNTIVO}\n"
            f"Analizza il bando e valuta la compatibilità del candidato (voto da 1 a 10) basandoti rigorosamente sul Profilo di Base e sui Dettagli CV.\n"
            f"Rispondi SOLO con JSON valido, nessun testo extra, nessun backtick:\n"
            f'{{"scadenza":"...","luogo":"...","requisiti":"...","borsa":"SI oppure NO","voto":7}}\n'
            f"TESTO: {testo[:40000]}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        
        # Pulizia del JSON se l'IA aggiunge blocchi markdown
        raw = response.text.strip().strip('`').replace('json', '', 1).strip()
        d = json.loads(raw)
        
        return (
            d.get("scadenza", "N.D."),
            d.get("luogo", "N.D."),
            d.get("requisiti", "N.D."),
            "SI" in str(d.get("borsa", "")).upper(),
            str(d.get("voto", "0"))
        )
    except Exception as e:
        logging.warning(f"Errore AI Gemini: {e}")
        return "Errore", "Errore", "Errore", False, "0"

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            main_c = soup.find('main') or soup
            
            for link_tag in main_c.find_all('a', href=True):
                href = link_tag['href'] # FIX: Niente .lower() qui, manteniamo il case originale del link!
                testo_l = link_tag.text.strip().lower()
                
                if any(x in href.lower() for x in BLACKLIST_DOMAINS) or any(x in testo_l for x in BLACKLIST_TEXT): continue
                if not any(x in testo_l for x in INCLUDE): continue
                
                # FIX: urljoin è il modo sicuro per costruire link relativi, come ha detto Claude
                real_url = href if href.startswith("http") else urljoin(url, href)
                id_bando = "uni_" + generate_hash(real_url)

                stato_attuale = memoria.get(id_bando, {}).get("stato")
                if stato_attuale in ["ignorato", "partecipo"]: continue
                if id_bando in memoria and stato_attuale == "nuovo":
                    # REMINDER — bando già visto ma non gestito
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
                    logging.info(f"🕵️ Analizzo il bando: {testo_l}")
                    testo_pdf = estrai_testo_da_url(real_url)
                    
                    # ⏳ FRENO A MANO: Aspetta 5 secondi per non farsi bloccare da Google
                    time.sleep(5) 
                    
                    scadenza, luogo, requisiti, borsa, voto = analizza_con_ai(testo_pdf)
                    
                    # 🛡️ PROTEZIONE: Se Gemini ha superato i limiti, NON bruciamo il bando. 
                    # Lo saltiamo e ci riproviamo alla prossima esecuzione del bot (tra 6 ore).
                    if scadenza == "Errore":
                        logging.warning("Rate limit di Gemini colpito. Salto per non bruciare il bando.")
                        continue 
                    
                    try:
                        score = int(''.join(filter(str.isdigit, str(voto))))
                        if score < 5:
                            # Se fa schifo, lo ignoriamo e lo salviamo per non rileggerlo più
                            memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                            continue
                    except:
                        score = 5

                    if is_scaduto(scadenza):
                        memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                        continue

                    msg = f"🎓 **BANDO ({score}/10)**\n\n📌 *{link_tag.text.strip()}*\n⏳ **Scadenza:** `{scadenza}`\n📝 **Requisiti:** _{requisiti}_\n💰 **Borsa:** {'✅' if borsa else '❌'}"
                    invia_telegram(msg, [
                        [{"text": "🌐 Apri Documento", "url": real_url}],
                        [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                         {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                        [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
                    ])
                    
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip(), "url": real_url, "tipo": "universita",
                        "funding": borsa, "scadenza": scadenza, "periodo": luogo, "requisiti": requisiti,
                        "voto": score, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("unigreen_worker", "ok")
    except Exception as e: 
        logging.error(f"Errore critico in unigreen_worker: {e}")
        update_health("unigreen_worker", f"error: {str(e)}")
    
    return memoria
