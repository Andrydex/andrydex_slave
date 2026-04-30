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

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

# Filtri per non impazzire
BLACKLIST_DOMAINS = ["facebook", "twitter", "instagram", "linkedin", "youtube", "radiofsc", "pica.cineca.it", "tel.unimore"]
BLACKLIST_TEXT = ["contatti", "privacy", "cookie", "newsletter", "magazine", "store", "amministrazione trasparente", "intranet", "sicurezza", "mappa", "feedback", "press room"]
INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "tutti i dipartimenti", "biagi", "finance", "student", "mobility", "erasmus", "mission", "avviso", "bando"]

PROFILO_UTENTE = "Studente di Economia (Dipartimento Biagi). Cerca: Mobilità internazionale, BIP, Erasmus, Borse di studio, Finanziamenti. Escludi: Giurisprudenza, Medicina, Lettere."

def estrai_testo_da_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=15, headers=headers)
        if response.status_code != 200: return ""
        
        # Se è un PDF, lo leggiamo con PyPDF2
        if url.lower().endswith(".pdf") or "application/pdf" in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                reader = PyPDF2.PdfReader(f)
                testo = ""
                # Leggiamo le prime 5 pagine (di solito bastano)
                for i in range(min(len(reader.pages), 5)):
                    testo += reader.pages[i].extract_text()
                return testo[:7000]
        
        # Se è una pagina HTML normale
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator=' ', strip=True)[:7000]
    except:
        return ""

def analizza_con_ai(testo):
    if not testo or not GEMINI_KEY: return "N.D.", "N.D.", False, "0"
    try:
        prompt = f"""
        PROFILO: {PROFILO_UTENTE}
        TESTO: {testo}
        
        Trova: 1.Scadenza (data o 'Scaduto'). 2.Svolgimento/Destinazione. 3.Borsa (SI/NO). 4.Compatibilità (1-10 per Economia).
        Rispondi SOLO con 4 righe formato 'Chiave: Valore'. Se non trovi nulla scrivi 'N.D.'.
        """
        risposta = model.generate_content(prompt).text.strip().split('\n')
        
        # Pulizia estrazione
        get_val = lambda x: x.split(":")[1].strip() if ":" in x else "N.D."
        return get_val(risposta[0]), get_val(risposta[1]), "SI" in risposta[2].upper(), get_val(risposta[3])
    except:
        return "Errore AI", "Errore AI", False, "0"

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            main = soup.find('main') or soup
            
            for link_tag in main.find_all('a', href=True):
                href = link_tag['href'].lower()
                testo_link = link_tag.text.strip().lower()
                
                if any(x in href for x in BLACKLIST_DOMAINS) or any(x in testo_link for x in BLACKLIST_TEXT): continue
                if not any(x in testo_link for x in INCLUDE): continue
                
                real_url = href if href.startswith("http") else ("https://www.unimore.it" + href if "unimore" in url else href)
                id_bando = "uni_" + generate_hash(real_url)

                if id_bando not in memoria:
                    print(f"🕵️ Analizzo: {testo_link}")
                    testo_completo = estrai_testo_da_url(real_url)
                    scadenza, periodo, borsa, voto = analizza_con_ai(testo_completo)
                    
                    # Filtro severo: se il voto è basso o non è un bando, lo scartiamo
                    try:
                        score = int(voto.split('/')[0]) if '/' in voto else int(voto)
                        if score < 5: 
                            memoria[id_bando] = {"stato": "ignorato"}
                            continue
                    except: pass

                    msg = f"🎓 **BANDO FILTRATO** ({voto}/10)\n\n📌 *{link_tag.text.strip()}*\n⏳ **Scadenza:** `{scadenza}`\n🌍 **Svolgimento:** `{periodo}`\n💰 **Borsa:** {'✅ SI' if borsa else '❌ NO'}"
                    invia_telegram(msg, [[{"text": "🌐 Apri Documento", "url": real_url}]])
                    
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip(), "url": real_url,
                        "tipo": "universita", "funding": borsa, "scadenza": scadenza,
                        "periodo": periodo, "voto": voto, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("unigreen_worker", "ok")
    except Exception as e:
        update_health("unigreen_worker", f"error: {str(e)}")
    return memoria
