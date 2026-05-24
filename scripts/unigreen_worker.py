import requests
import os
import io
import json
import re
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# Flag globale: True se la quota GIORNALIERA è esaurita (inutile riprovare)
_quota_giornaliera_esaurita = False

URLS = {
    "Unimore Bandi": "https://www.unimore.it/it/ateneo/bandi",
    "UniGreen Events": "https://unigreen-alliance.eu/events/list/",
    "UniGreen Mobility": "https://unigreen-alliance.eu/mobility/blended-intensive-programs-bip/",
    "CLUST-ER Bandi": "https://www.clust-er.it/bandi/",
    "CLUST-ER Eventi": "https://www.clust-er.it/eventi/",
    "Spazio Aperto Modena": "https://spazioapertomodena.it/",
    "Emilia Romagna Startup Bandi": "https://www.emiliaromagnastartup.it/it/bandi",
    "Emilia Romagna Startup Call": "https://www.emiliaromagnastartup.it/it/call",
}

BLACKLIST_DOMAINS = [
    "facebook", "twitter", "instagram", "linkedin", "youtube",
    "pica.cineca.it", "tel.unimore", "mailto:"
]
BLACKLIST_TEXT = [
    "contatti", "privacy", "cookie", "newsletter", "magazine",
    "amministrazione trasparente", "intranet", "sicurezza"
]
INCLUDE = [
    "economia", "unigreen", "bip", "intensive", "mobilità", "biagi",
    "finance", "erasmus", "student", "mobility", "bando", "avviso", "selezione",
    "call", "opportunit", "esperien", "startup", "innovazione", "evento"
]

# Parole-chiave che devono essere presenti nel testo per giustificare una chiamata Gemini.
# Se nessuna è presente, la pagina non è un vero bando e si skippa l'AI.
KEYWORDS_BANDO = [
    "scadenza", "deadline", "candidature", "candidarsi", "candidati",
    "application", "submission", "apply", "domanda di", "presenta la domanda",
    "iscrizione", "modulo", "partecipa", "ammissione", "selezione",
    "entro il", "entro le ore", "aperto fino", "open until",
    "borsa", "scholarship", "grant", "finanziamento", "contributo"
]

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
    return contesto[:10000]


CONTESTO_AGGIUNTIVO = carica_contesto_pdf()


def is_scaduto(scadenza_str):
    if not scadenza_str or scadenza_str in ("N.D.", "Errore"):
        return False
    mesi = {
        "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
        "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
        "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12"
    }
    s = scadenza_str.lower().strip()
    for m, num in mesi.items():
        s = s.replace(m, num)
    match = re.search(r'(\d{1,2})[\s\/\-](\d{1,2})[\s\/\-](\d{4})', s)
    if match:
        g, m, a = match.groups()
        try:
            return datetime(int(a), int(m), int(g)) < datetime.now()
        except Exception:
            pass
    return False


def normalizza_scadenza(s):
    if not s:
        return "N.D."
    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', s.strip()):
        return s.strip()
    return "N.D."


def ha_keywords_bando(testo):
    """
    Pre-filter leggero: restituisce True se il testo contiene almeno una
    parola-chiave tipica di un bando reale. Evita di chiamare Gemini su
    pagine di navigazione o articoli generici.
    """
    testo_lower = testo.lower()
    return any(k in testo_lower for k in KEYWORDS_BANDO)


def estrai_testo_da_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=25, headers=headers)
        if response.status_code != 200:
            return ""

        if url.lower().endswith(".pdf") or "application/pdf" in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                testo = ""
                pagine = list(range(min(15, num_pages)))
                if num_pages > 15:
                    pagine.extend(range(max(15, num_pages - 15), num_pages))
                for i in sorted(list(set(pagine))):
                    testo += reader.pages[i].extract_text() + "\n"
                return testo[:50000]

        soup = BeautifulSoup(response.text, "html.parser")
        testo_pagina = soup.get_text(separator=' ', strip=True)
        testo_allegati = "\n\n--- TESTO ALLEGATI TROVATI NELLA PAGINA ---\n"
        trovati = False
        main_content = soup.find('main') or soup.find('body') or soup

        for a_tag in main_content.find_all('a', href=True):
            href = a_tag['href']
            testo_link = a_tag.text.lower()
            if ".pdf" in href.lower() or any(k in testo_link for k in ["bando", "avviso", "allegato", "scarica"]):
                pdf_url = href if href.startswith("http") else urljoin(url, href)
                if pdf_url == url:
                    continue
                try:
                    pdf_resp = requests.get(pdf_url, timeout=15, headers=headers)
                    if "application/pdf" in pdf_resp.headers.get('Content-Type', '') or pdf_url.lower().endswith(".pdf"):
                        trovati = True
                        with io.BytesIO(pdf_resp.content) as f:
                            reader = pypdf.PdfReader(f)
                            for page in reader.pages[:20]:
                                testo_allegati += page.extract_text() + "\n"
                except Exception as e:
                    logging.warning(f"Impossibile leggere allegato {pdf_url}: {e}")

        testo_finale = testo_pagina
        if trovati:
            testo_finale += testo_allegati
        return testo_finale[:50000]

    except Exception as e:
        logging.warning(f"Errore estrazione da {url}: {e}")
        return ""


def analizza_con_ai(testo):
    """
    Chiama Gemini per analizzare il testo.
    - Se la quota giornaliera è esaurita, restituisce Errore senza chiamare l'API.
    - Se arriva un 429 per limite al minuto, aspetta il tempo suggerito e riprova una volta.
    - Se arriva un 429 per quota giornaliera, imposta il flag e si ferma.
    """
    global _quota_giornaliera_esaurita

    if _quota_giornaliera_esaurita:
        return {"scadenza": "Errore"}

    if not testo or not client:
        return {"scadenza": "N.D.", "voto": "0"}

    def _chiama_gemini():
        prompt = (
            f"PROFILO DI BASE: {PROFILO_UTENTE}\n"
            f"DETTAGLI CV/PROFILO (dal PDF): {CONTESTO_AGGIUNTIVO}\n"
            f"Analizza questo testo. "
            f"REGOLA 1 (PAGINA GENERICA): Se il testo è solo una pagina informativa, un articolo, o NON ha una scadenza definita per candidarsi, assegna 'voto': 1 e 'scadenza': 'N.D.'. "
            f"REGOLA 2 (DIPARTIMENTI): Se il bando specifica dipartimenti o corsi ammessi e DCI/Economia/Biagi non è incluso, assegna 'voto': 1 e scrivi quali dipartimenti sono ammessi nel campo 'requisiti'. "
            f"REGOLA 3 (DOTTORATI): Se il bando richiede laurea già conseguita o è per dottorandi, assegna 'voto': 1. "
            f"Valuta 6-10 SOLO se il bando è concretamente accessibile a uno studente magistrale iscritto al 1° anno di DCI.\n"
            f"Rispondi SOLO con JSON valido, nessun testo extra, nessun backtick:\n"
            f'{{"scadenza":"DD/MM/YYYY oppure esattamente N.D.","luogo":"...","durata":"...","ente":"...","argomenti":"...","requisiti":"...","voto":7}}\n'
            f"IMPORTANTE: 'scadenza' deve essere SOLO DD/MM/YYYY oppure esattamente N.D., mai testo libero.\n"
            f"TESTO: {testo[:40000]}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw = response.text.strip().strip('`').replace('json', '', 1).strip()
        return json.loads(raw)

    try:
        return _chiama_gemini()
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            # Distingui quota giornaliera da rate limit al minuto
            if "PerDay" in err or "per_day" in err.lower() or "free_tier" in err.lower():
                _quota_giornaliera_esaurita = True
                logging.warning("🚫 Quota Gemini GIORNALIERA esaurita. Analisi AI sospesa per oggi.")
                return {"scadenza": "Errore"}
            else:
                # Rate limit al minuto: estrai il tempo di attesa e riprova
                wait_match = re.search(r'retry in (\d+(?:\.\d+)?)s', err)
                wait_sec = float(wait_match.group(1)) if wait_match else 60
                wait_sec = min(wait_sec + 5, 120)  # max 2 minuti di attesa
                logging.warning(f"⏳ Rate limit Gemini (al minuto), aspetto {wait_sec:.0f}s e riprovo...")
                time.sleep(wait_sec)
                try:
                    return _chiama_gemini()
                except Exception as e2:
                    err2 = str(e2)
                    if "429" in err2 and ("PerDay" in err2 or "free_tier" in err2.lower()):
                        _quota_giornaliera_esaurita = True
                        logging.warning("🚫 Quota Gemini GIORNALIERA esaurita dopo retry.")
                    else:
                        logging.warning(f"Errore AI Gemini dopo retry: {e2}")
                    return {"scadenza": "Errore"}
        else:
            logging.warning(f"Errore AI Gemini: {e}")
            return {"scadenza": "Errore"}


def _invia_reminder(id_bando, dati):
    msg_r = (
        f"⏳ *REMINDER BANDO ({dati.get('voto', '?')}/10)*\n\n"
        f"📌 *{dati.get('titolo', '')}*\n"
        f"⏳ **Scadenza:** `{dati.get('scadenza', 'N.D.')}`\n"
        f"📝 **Requisiti:** _{dati.get('requisiti', 'N.D.')}_"
    )
    invia_telegram(msg_r, [
        [{"text": "🌐 Apri Documento", "url": dati.get("url", "")}],
        [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
         {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
        [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
    ])


def run_unigreen_worker(memoria):
    global _quota_giornaliera_esaurita
    try:
        # FASE 0: Reminder sweep indipendente dal crawler
        logging.info("📋 Avvio reminder sweep bandi universitari...")
        for id_bando, dati in list(memoria.items()):
            if not isinstance(dati, dict):
                continue
            if dati.get("tipo") != "universita":
                continue
            if dati.get("stato") != "nuovo":
                continue
            scadenza_salvata = normalizza_scadenza(str(dati.get("scadenza", "N.D.")))
            if scadenza_salvata == "N.D.":
                logging.info(f"🗑 Bando con scadenza N.D. rimosso: {id_bando}")
                memoria[id_bando]["stato"] = "ignorato"
                continue
            if is_scaduto(scadenza_salvata):
                logging.info(f"🗑 Bando scaduto rimosso: {dati.get('titolo', id_bando)}")
                memoria[id_bando]["stato"] = "ignorato"
                continue
            logging.info(f"⏳ Reminder: {dati.get('titolo', id_bando)[:40]}")
            _invia_reminder(id_bando, dati)

        # FASE 1: Raccolta link (Livello 1)
        queue = []
        visti = set()

        for nome_fonte, url in URLS.items():
            try:
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, "html.parser")
                main_c = soup.find('main') or soup
                for link_tag in main_c.find_all('a', href=True):
                    href = link_tag['href']
                    testo_l = link_tag.text.strip().lower()
                    if any(x in href.lower() for x in BLACKLIST_DOMAINS):
                        continue
                    if any(x in testo_l for x in BLACKLIST_TEXT):
                        continue
                    if not any(x in testo_l for x in INCLUDE):
                        continue
                    real_url = href if href.startswith("http") else urljoin(url, href)
                    if real_url not in visti:
                        visti.add(real_url)
                        queue.append({"titolo": link_tag.text.strip(), "url": real_url, "depth": 1})
            except Exception as e:
                logging.warning(f"Errore radice {url}: {e}")

        # FASE 2: Analisi coda
        while queue:
            if _quota_giornaliera_esaurita:
                logging.warning("⛔ Quota giornaliera esaurita, interrompo crawler universitario.")
                break

            item = queue.pop(0)
            titolo_link = item["titolo"]
            real_url = item["url"]
            depth = item["depth"]

            id_bando = "uni_" + generate_hash(real_url)
            stato_attuale = memoria.get(id_bando, {}).get("stato")

            if stato_attuale in ["ignorato", "partecipo", "nuovo"]:
                continue

            logging.info(f"🕵️ Scarico (Livello {depth}): {titolo_link[:40]}...")
            testo_pdf = estrai_testo_da_url(real_url)

            # PRE-FILTER: se il testo non contiene parole-chiave di bando, skippa Gemini
            if not ha_keywords_bando(testo_pdf):
                logging.info(f"⏭ Nessuna keyword di bando trovata, skippo AI per: {titolo_link[:40]}")
                memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                # Crawl depth-2 comunque: potrebbe essere una pagina hub
                if depth < 2:
                    try:
                        sub_resp = requests.get(real_url, timeout=15)
                        sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                        sub_main = sub_soup.find('main') or sub_soup
                        for sub_a in sub_main.find_all('a', href=True):
                            s_href = sub_a['href']
                            s_testo = sub_a.text.strip().lower()
                            if any(x in s_href.lower() for x in BLACKLIST_DOMAINS):
                                continue
                            if any(x in s_testo for x in BLACKLIST_TEXT):
                                continue
                            if not any(x in s_testo for x in INCLUDE):
                                continue
                            next_url = s_href if s_href.startswith("http") else urljoin(real_url, s_href)
                            if next_url not in visti:
                                visti.add(next_url)
                                queue.append({"titolo": sub_a.text.strip(), "url": next_url, "depth": depth + 1})
                    except Exception:
                        pass
                continue

            # Ha le keyword: vale la pena chiamare Gemini
            logging.info(f"🤖 Analizzo con AI (Livello {depth}): {titolo_link[:40]}...")
            time.sleep(15)  # Pausa più generosa tra le chiamate AI
            dati_ai = analizza_con_ai(testo_pdf)

            if _quota_giornaliera_esaurita:
                logging.warning("⛔ Quota esaurita dopo analisi, interrompo.")
                break

            scadenza = normalizza_scadenza(str(dati_ai.get("scadenza", "N.D.")))
            if str(dati_ai.get("scadenza", "")) == "Errore":
                continue

            try:
                score = int(''.join(filter(str.isdigit, str(dati_ai.get("voto", "5")))))
            except Exception:
                score = 5

            if score < 5 or scadenza == "N.D.":
                memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                if depth < 2:
                    logging.info(f"🔄 Score basso/scadenza N.D., estraggo sotto-link da: {real_url}")
                    try:
                        sub_resp = requests.get(real_url, timeout=15)
                        sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                        sub_main = sub_soup.find('main') or sub_soup
                        for sub_a in sub_main.find_all('a', href=True):
                            s_href = sub_a['href']
                            s_testo = sub_a.text.strip().lower()
                            if any(x in s_href.lower() for x in BLACKLIST_DOMAINS):
                                continue
                            if any(x in s_testo for x in BLACKLIST_TEXT):
                                continue
                            if not any(x in s_testo for x in INCLUDE):
                                continue
                            next_url = s_href if s_href.startswith("http") else urljoin(real_url, s_href)
                            if next_url not in visti:
                                visti.add(next_url)
                                queue.append({"titolo": sub_a.text.strip(), "url": next_url, "depth": depth + 1})
                    except Exception:
                        pass
                continue

            if is_scaduto(scadenza):
                memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                continue

            msg = (
                f"🎓 *BANDO ({score}/10)*\n\n"
                f"📌 *{titolo_link}*\n"
                f"🏢 **Ente:** {dati_ai.get('ente', 'N.D.')}\n"
                f"⏳ **Scadenza:** `{scadenza}`\n"
                f"📝 **Requisiti:** _{dati_ai.get('requisiti', 'N.D.')}_"
            )
            invia_telegram(msg, [
                [{"text": "🌐 Apri Documento", "url": real_url}],
                [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                 {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
            ])

            memoria[id_bando] = {
                "stato": "nuovo",
                "titolo": titolo_link,
                "url": real_url,
                "tipo": "universita",
                "scadenza": scadenza,
                "luogo": dati_ai.get("luogo", "N.D."),
                "durata": dati_ai.get("durata", "N.D."),
                "ente": dati_ai.get("ente", "N.D."),
                "argomenti": dati_ai.get("argomenti", "N.D."),
                "requisiti": dati_ai.get("requisiti", "N.D."),
                "voto": score,
                "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
            }

        update_health("unigreen_worker", "ok")

    except Exception as e:
        logging.error(f"Errore critico in unigreen_worker: {e}")
        update_health("unigreen_worker", f"error: {str(e)}")

    return memoria
