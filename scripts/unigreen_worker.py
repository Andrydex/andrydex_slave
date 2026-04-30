import requests
import os
import io
import pypdf
from google import genai # <--- NUOVO IMPORT
from bs4 import BeautifulSoup
from hashing import generate_hash
from telegram_sender import invia_telegram
from health_check import update_health
from datetime import datetime

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client = None
if GEMINI_KEY:
    # Nuovo modo di inizializzare Gemini nel 2026
    client = genai.Client(api_key=GEMINI_KEY)

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/"
}

BLACKLIST_DOMAINS = ["facebook", "twitter", "instagram", "linkedin", "youtube", "pica.cineca.it", "tel.unimore"]
BLACKLIST_TEXT = ["contatti", "privacy", "cookie", "newsletter", "magazine", "amministrazione trasparente", "intranet", "sicurezza"]
INCLUDE = ["economia", "unigreen", "bip", "intensive", "mobilità", "biagi", "finance", "erasmus", "student", "mobility"]
PROFILO_UTENTE = "Studente di Economia (Dipartimento Biagi). Cerca: Mobilità internazionale, BIP, Erasmus, Borse di studio. Escludi: Giurisprudenza, Medicina."

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
    except: return ""

def analizza_con_ai(testo):
    if not testo or not client: return "N.D.", "N.D.", "N.D.", False, "0"
    try:
        prompt = f"PROFILO: {PROFILO_UTENTE}\nAnalizza il bando e trova: 1.Scadenza. 2.Destinazione. 3.Requisiti brevi. 4.Borsa(SI/NO). 5.Voto compatibilità(1-10).\nRispondi in 5 righe 'K: V'.\nTESTO: {testo}"
        # Nuova sintassi generate_content
        response = client.models.generate_content(model='gemini-3-flash', contents=prompt)
        risposta = response.text.strip().split('\n')
        get_v = lambda i: risposta[i].split(":")[1].strip() if ":" in risposta[i] else "N.D."
        return get_v(0), get_v(1), get_v(2), "SI" in get_v(3).upper(), get_v(4)
    except Exception as e:
        print(f"Errore AI: {e}")
        return "Errore", "Errore", "Errore", False, "0"

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            main_c = soup.find('main') or soup
            for link_tag in main_c.find_all('a', href=True):
                href, testo_l = link_tag['href'].lower(), link_tag.text.strip().lower()
                if any(x in href for x in BLACKLIST_DOMAINS) or any(x in testo_l for x in BLACKLIST_TEXT): continue
                if not any(x in testo_l for x in INCLUDE): continue
                real_url = href if href.startswith("http") else ("https://www.unimore.it" + href if "unimore" in url else href)
                id_bando = "uni_" + generate_hash(real_url)
                if id_bando not in memoria:
                    print(f"🕵️ Analizzo: {testo_l}")
                    testo_pdf = estrai_testo_da_url(real_url)
                    scadenza, luogo, requisiti, borsa, voto = analizza_con_ai(testo_pdf)
                    try:
                        score = int(''.join(filter(str.isdigit, voto)))
                        if score < 5: 
                            memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                            continue
                    except: score = 5
                    msg = f"🎓 **BANDO ({score}/10)**\n\n📌 *{link_tag.text.strip()}*\n⏳ **Scadenza:** `{scadenza}`\n📝 **Requisiti:** _{requisiti}_\n💰 **Borsa:** {'✅' if borsa else '❌'}"
                    invia_telegram(msg, [[{"text": "🌐 Apri", "url": real_url}]])
                    memoria[id_bando] = {
                        "stato": "nuovo", "titolo": link_tag.text.strip(), "url": real_url, "tipo": "universita",
                        "funding": borsa, "scadenza": scadenza, "periodo": luogo, "requisiti": requisiti,
                        "voto": score, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                    }
        update_health("unigreen_worker", "ok")
    except Exception as e: update_health("unigreen_worker", f"error: {str(e)}")
    return memoria
