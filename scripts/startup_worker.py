import requests
import os
import io
import json
import re
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# Flag globale: True se la quota GIORNALIERA è esaurita (inutile riprovare)
_quota_giornaliera_esaurita = False

URLS_STARTUP = {
    "ART-ER (Emilia Romagna)": "https://www.art-er.it/bandi/",
    "BI-REX": "https://bi-rex.it/bandi-e-call/",
    "EXO Molise": "https://www.exomolise.it/bandi/",
    "Invitalia (Nazionali)": "https://www.invitalia.it/cosa-facciamo/creiamo-nuove-aziende",
    "CLUST-ER Bandi": "https://www.clust-er.it/bandi/",
    "CLUST-ER Eventi": "https://www.clust-er.it/eventi/",
    "Spazio Aperto Modena": "https://spazioapertomodena.it/",
    "Emilia Romagna Startup": "https://www.emiliaromagnastartup.it/",
    "Regione Molise (Bandi)": "https://www.regione.molise.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/1"
}

# Keywords per filtrare i LINK da accodare (già presenti)
KEYWORDS_STARTUP = [
    "bando", "startup", "agevolazione", "contributo", "finanziamento",
    "imprese", "innovazione", "incentiv", "smart", "fondo", "misura", "nuove-aziende"
]

# Keywords per il PRE-FILTER AI: deve essere presente almeno una
# prima di chiamare Gemini, altrimenti è sicuramente una pagina generica
KEYWORDS_BANDO_REALE = [
    "scadenza", "deadline", "candidature", "candidarsi", "presenta la domanda",
    "domanda di partecipazione", "iscrizione", "modulo di", "sportello aperto",
    "apertura sportello", "finestra", "entro il", "entro le ore", "aperto fino",
    "open until", "contributo a fondo perduto", "finanziamento agevolato",
    "presentazione delle domande", "invio della domanda"
]

BLACKLIST_LINKS = ["facebook", "twitter", "instagram", "linkedin", "youtube", "mailto:"]


def carica_tutti_i_pdf():
    testo = "--- PROFILO FOUNDER E IDEA DI STARTUP ---\n"
    cartella = "context"
    if not os.path.exists(cartella):
        return testo
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


def normalizza_scadenza(s):
    if not s:
        return "N.D."
    s = s.strip()
    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', s):
        return s
    if s.lower() == "sportello":
        return "Sportello"
    return "N.D."


def is_scaduto(scadenza_str):
    if not scadenza_str or scadenza_str in ("N.D.", "Errore", "Sportello"):
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


def ha_keywords_bando_reale(testo):
    """
    Pre-filter: restituisce True se il testo contiene almeno una parola-chiave
    tipica di un bando con scadenza reale. Evita di chiamare Gemini su pagine
    di navigazione, articoli, o landing page generiche.
    """
    testo_lower = testo.lower()
    return any(k in testo_lower for k in KEYWORDS_BANDO_REALE)


def estrai_testo_startup(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, timeout=25, headers=headers)
        if response.status_code != 200:
            return ""

        if url.lower().endswith(".pdf") or "application/pdf" in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                return "".join([p.extract_text() for p in pypdf.PdfReader(f).pages[:15]])[:50000]

        soup = BeautifulSoup(response.text, "html.parser")
        testo_pagina = soup.get_text(separator=' ', strip=True)
        testo_allegati = "\n--- ALLEGATI ---\n"
        trovati = False

        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if ".pdf" in href.lower() or any(k in a_tag.text.lower() for k in ["bando", "avviso", "scarica", "allegato"]):
                pdf_url = href if href.startswith("http") else urljoin(url, href)
                if pdf_url == url:
                    continue
                try:
                    pdf_resp = requests.get(pdf_url, timeout=15, headers=headers)
                    if "application/pdf" in pdf_resp.headers.get('Content-Type', '') or pdf_url.lower().endswith(".pdf"):
                        trovati = True
                        with io.BytesIO(pdf_resp.content) as f:
                            testo_allegati += "".join([p.extract_text() for p in pypdf.PdfReader(f).pages[:10]])
                except Exception as e:
                    logging.warning(f"Errore sotto-link startup: {e}")

        return (testo_pagina + (testo_allegati if trovati else ""))[:50000]
    except Exception:
        return ""


def analizza_startup_con_ai(testo):
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
            f"DATI DEL PROGETTO E DEL SOLO FOUNDER:\n{CONTESTO_STARTUP}\n\n"
            f"Analizza questo testo. "
            f"REGOLA 1 (PAGINA GENERICA): Se il testo è solo una pagina informativa o NON c'è un modo chiaro per candidarsi, assegna 'voto': 1 e 'scadenza': 'N.D.'. "
            f"REGOLA 2 (SPORTELLO): Se il bando è a sportello senza scadenza fissa, scrivi esattamente 'Sportello' nel campo scadenza. "
            f"Valuta 6-10 SOLO se è un vero bando/agevolazione attivo e compatibile con il profilo.\n"
            f"Rispondi SOLO con JSON valido, nessun backtick o testo extra:\n"
            f'{{"scadenza":"DD/MM/YYYY oppure Sportello oppure esattamente N.D.","ente":"...","requisiti":"...","tipo_fondo":"Fondo perduto / Finanziamento agevolato / Altro","voto":7}}\n'
            f"IMPORTANTE: 'scadenza' deve essere SOLO una data DD/MM/YYYY, la parola Sportello, oppure esattamente N.D. Mai testo libero.\n"
            f"TESTO BANDO: {testo[:30000]}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw = response.text.strip().strip('`').replace('json', '', 1).strip()
        return json.loads(raw)

    try:
        return _chiama_gemini()
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            if "PerDay" in err or "per_day" in err.lower() or "free_tier" in err.lower():
                _quota_giornaliera_esaurita = True
                logging.warning("🚫 Quota Gemini GIORNALIERA esaurita. Analisi AI sospesa per oggi.")
                return {"scadenza": "Errore"}
            else:
                wait_match = re.search(r'retry in (\d+(?:\.\d+)?)s', err)
                wait_sec = float(wait_match.group(1)) if wait_match else 60
                wait_sec = min(wait_sec + 5, 120)
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


def _invia_reminder_startup(id_bando, dati):
    msg_r = (
        f"⏳ *REMINDER STARTUP ({dati.get('voto', '?')}/10)*\n\n"
        f"📌 *{dati.get('titolo', '')}*\n"
        f"⏳ **Scadenza:** `{dati.get('scadenza', 'N.D.')}`\n"
        f"📝 **Requisiti:** _{dati.get('requisiti', 'N.D.')}_"
    )
    invia_telegram(msg_r, [
        [{"text": "🌐 Vai al Bando", "url": dati.get("url", "")}],
        [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
         {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
        [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
    ])


def run_startup_worker(memoria):
    global _quota_giornaliera_esaurita
    try:
        # FASE 0: Reminder sweep indipendente dal crawler
        logging.info("📋 Avvio reminder sweep bandi startup...")
        for id_bando, dati in list(memoria.items()):
            if not isinstance(dati, dict):
                continue
            if dati.get("tipo") != "startup":
                continue
            if dati.get("stato") != "nuovo":
                continue
            scadenza_salvata = normalizza_scadenza(str(dati.get("scadenza", "N.D.")))
            if scadenza_salvata == "N.D.":
                logging.info(f"🗑 Startup con scadenza N.D. rimossa: {id_bando}")
                memoria[id_bando]["stato"] = "ignorato"
                continue
            if is_scaduto(scadenza_salvata):
                logging.info(f"🗑 Startup scaduta rimossa: {dati.get('titolo', id_bando)}")
                memoria[id_bando]["stato"] = "ignorato"
                continue
            logging.info(f"⏳ Reminder startup: {dati.get('titolo', id_bando)[:40]}")
            _invia_reminder_startup(id_bando, dati)

        # FASE 1: Raccolta link (Livello 1)
        queue = []
        visti = set()

        for nome_fonte, url in URLS_STARTUP.items():
            try:
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, "html.parser")
                for link_tag in soup.find_all('a', href=True):
                    href = link_tag['href']
                    href_lower = href.lower()
                    testo_l = link_tag.text.strip().lower()
                    if any(x in href_lower for x in BLACKLIST_LINKS):
                        continue
                    if not any(k in testo_l for k in KEYWORDS_STARTUP) and not any(k in href_lower for k in KEYWORDS_STARTUP):
                        continue
                    real_url = href if href.startswith("http") else urljoin(url, href)
                    if real_url == url:
                        continue
                    if real_url not in visti:
                        visti.add(real_url)
                        queue.append({"titolo": link_tag.text.strip(), "url": real_url, "depth": 1})
            except Exception as e:
                logging.warning(f"Errore radice startup {url}: {e}")

        # FASE 2: Analisi coda
        while queue:
            if _quota_giornaliera_esaurita:
                logging.warning("⛔ Quota giornaliera esaurita, interrompo crawler startup.")
                break

            item = queue.pop(0)
            titolo_link = item["titolo"]
            real_url = item["url"]
            depth = item["depth"]

            id_bando = "start_" + generate_hash(real_url)
            stato_attuale = memoria.get(id_bando, {}).get("stato")

            if stato_attuale in ["ignorato", "partecipo", "nuovo"]:
                continue

            logging.info(f"🕵️ Scarico (Livello {depth}): {titolo_link[:40] or real_url[:40]}...")
            testo_completo = estrai_testo_startup(real_url)

            # PRE-FILTER: se non ci sono keyword di bando reale, skippa Gemini
            if not ha_keywords_bando_reale(testo_completo):
                logging.info(f"⏭ Nessuna keyword di bando trovata, skippo AI per: {titolo_link[:40]}")
                memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                if depth < 2:
                    try:
                        sub_resp = requests.get(real_url, timeout=15)
                        sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                        for sub_a in sub_soup.find_all('a', href=True):
                            s_href = sub_a.get('href', '')
                            s_href_lower = s_href.lower()
                            s_testo = sub_a.text.strip().lower()
                            if any(x in s_href_lower for x in BLACKLIST_LINKS):
                                continue
                            if not any(k in s_testo for k in KEYWORDS_STARTUP) and not any(k in s_href_lower for k in KEYWORDS_STARTUP):
                                continue
                            next_url = s_href if s_href.startswith("http") else urljoin(real_url, s_href)
                            if next_url not in visti:
                                visti.add(next_url)
                                queue.append({"titolo": sub_a.text.strip(), "url": next_url, "depth": depth + 1})
                    except Exception as e:
                        logging.warning(f"Errore esplorazione sotto-link: {e}")
                continue

            # Ha le keyword: vale la pena chiamare Gemini
            logging.info(f"🤖 Analizzo con AI (Livello {depth}): {titolo_link[:40]}...")
            time.sleep(15)
            dati_ai = analizza_startup_con_ai(testo_completo)

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
                    logging.info(f"🔄 Score basso/scadenza N.D., esploro sotto-link da: {real_url}")
                    try:
                        sub_resp = requests.get(real_url, timeout=15)
                        sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                        for sub_a in sub_soup.find_all('a', href=True):
                            s_href = sub_a.get('href', '')
                            s_href_lower = s_href.lower()
                            s_testo = sub_a.text.strip().lower()
                            if any(x in s_href_lower for x in BLACKLIST_LINKS):
                                continue
                            if not any(k in s_testo for k in KEYWORDS_STARTUP) and not any(k in s_href_lower for k in KEYWORDS_STARTUP):
                                continue
                            next_url = s_href if s_href.startswith("http") else urljoin(real_url, s_href)
                            if next_url not in visti:
                                visti.add(next_url)
                                queue.append({"titolo": sub_a.text.strip(), "url": next_url, "depth": depth + 1})
                    except Exception as e:
                        logging.warning(f"Errore esplorazione sotto-link: {e}")
                continue

            if is_scaduto(scadenza):
                memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                continue

            ente = dati_ai.get('ente', 'N.D.')
            tipo_fondo = dati_ai.get('tipo_fondo', 'N.D.')
            requisiti = dati_ai.get('requisiti', 'N.D.')

            msg = (
                f"🚀 *BANDO STARTUP ({score}/10)*\n\n"
                f"📌 *{titolo_link or 'Vedi link'}*\n"
                f"🏢 **Ente:** {ente}\n"
                f"⏳ **Scadenza:** `{scadenza}`\n"
                f"💰 **Tipo:** {tipo_fondo}\n"
                f"📝 **Requisiti:** _{requisiti}_"
            )
            invia_telegram(msg, [
                [{"text": "🌐 Vai al Bando", "url": real_url}],
                [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                 {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
            ])

            memoria[id_bando] = {
                "stato": "nuovo",
                "titolo": titolo_link or "Bando Startup",
                "url": real_url,
                "tipo": "startup",
                "scadenza": scadenza,
                "ente": ente,
                "requisiti": requisiti,
                "fondo": tipo_fondo,
                "voto": score,
                "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
            }

        update_health("startup_worker", "ok")

    except Exception as e:
        logging.error(f"Errore startup_worker: {e}")
        update_health("startup_worker", f"error: {str(e)}")

    return memoria
