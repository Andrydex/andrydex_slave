import requests
import os
import io
import PyPDF2
import google.generativeai as genai
from bs4 import BeautifulSoup
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health
from datetime import datetime

# Configurazione API con il modello di punta del 2026
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # Utilizziamo Gemini 3 Flash: velocità e finestra di contesto enorme
    model = genai.GenerativeModel('gemini-3-flash')

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

# Filtri di sicurezza per evitare spam
BLACKLIST_DOMAINS = ["facebook", "twitter", "instagram", "linkedin", "youtube", "radiofsc", "pica.cineca.it", "tel.unimore"]
BLACKLIST_TEXT = ["contatti", "privacy", "cookie", "newsletter", "magazine", "store", "amministrazione trasparente", "intranet", "sicurezza", "mappa", "feedback", "press room"]
INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "tutti i dipartimenti", "biagi", "finance", "student", "mobility", "erasmus", "mission", "avviso", "bando"]

# Il tuo profilo per l'analisi intelligente
PROFILO_UTENTE = "Studente di Economia (Dipartimento Biagi). Cerca: Mobilità internazionale, BIP, Erasmus, Borse di studio, Finanziamenti. Escludi: Giurisprudenza, Medicina, Lettere."

def estrai_testo_da_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=25, headers=headers)
        if response.status_code != 200: return ""
        
        # Lettura profonda PDF (fino a 30 pagine)
        if url.lower().endswith(".pdf") or "application/pdf" in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                reader = PyPDF2.PdfReader(f)
                testo = ""
                for i in range(min(len(reader.pages), 30)):
                    testo += reader.pages[i].extract_text() + "\n"
                return testo[:50000] # Alziamo a 50k per Gemini 3
        
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator=' ', strip=True)[:50000]
    except:
        return ""

def analizza_con_ai(testo):
    if not testo or not GEMINI_KEY: return "N.D.", "N.D.", "N.D.", False, "0"
    try:
        # Prompt ottimizzato per Gemini 3
        prompt = f"""
        PROFILO TARGET: {PROFILO_UTENTE}
        
        Analizza questo bando universitario e agisci come un esperto consulente di carriera. 
        Scansiona l'intero testo per trovare:
        1. Scadenza (Data ultima, se passata scrivi 'SCADUTO').
        2. Svolgimento/Destinazione (Luogo, date o 'Da definire').
        3. Requisiti Chiave (Sii specifico: media voti, anno di corso, dipartimento).
        4. Borsa di Studio (SI/NO - Conferma se coprono spese o tasse).
        5. Compatibilità (Voto 1-10 per il profilo indicato).

        Rispondi ESCLUSIVAMENTE in questo formato:
        S: [valore]
        D: [valore]
        R: [valore]
        B: [SI/NO]
        V: [voto]

        TESTO: {testo}
        """
        risposta = model.generate_content(prompt).text.strip().split('\n')
        
        def clean(idx): return risposta[idx].split(":")[1].strip() if ":" in risposta[idx] else "N.D."

        return clean(0), clean(1), clean(2), "SI" in clean(3).upper(), clean(4)
    except:
        return "Errore", "Errore", "Errore", False, "0"

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            # Cerchiamo solo nell'area dei contenuti
            content_area = soup.find('main') or soup.find('article') or soup
            
            for link_tag in content_area.find_all('a', href=True):
                href, testo_l = link_tag['href'].lower(), link_tag.text.strip().lower()
                
                if any(x in href for x in BLACKLIST_DOMAINS) or any(x in testo_l for x in BLACKLIST_TEXT): continue
                if not any(x in testo_l for x in INCLUDE): continue
                
                real_url = href if href.startswith("http") else ("https://www.unimore.it" + href if "unimore" in url else href)
                id_bando = "uni_" + generate_hash(real_url)

                if id_bando not in memoria:
                    print(f"🧠 Gemini 3 sta leggendo: {link_tag.text.strip()}")
                    testo_bando = estrai_testo_da_url(real_url)
                    scadenza, periodo, requisiti, borsa, voto = analizza_con_ai(testo_bando)
                    
                    # Filtro basato sul voto di compatibilità dell'AI
                    try:
                        score = int(''.join(filter(str.isdigit, voto)))
                        if score < 5: 
                            memoria[id_bando] = {"stato": "ignorato"}
                            continue
                    except: score = 5

                    msg = (
                        f"🎓 **BANDO SELEZIONATO** ({score}/10)\n\n"
                        f"📌 *{link_tag.text.strip()}*\n"
                        f"⏳ **Scadenza:** `{scadenza}`\n"
                        f"🌍 **Svolgimento:** `{periodo}`\n"
                        f"📝 **Requisiti:** _{requisiti}_\n"
                        f"💰 **Borsa:** {'✅ SI' if borsa else '❌ NO'}"
                    )
                    invia_telegram(msg, [[{"text": "🌐 Documento", "url": real_url}]])
                    
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip(), "url": real_url,
                        "tipo": "universita", "funding": borsa, "scadenza": scadenza,
                        "periodo": periodo, "requisiti": requisiti, "voto": score, 
                        "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("unigreen_worker", "ok")
    except Exception as e:
        update_health("unigreen_worker", f"error: {str(e)}")
    return memoria
