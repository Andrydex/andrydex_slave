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

PROFILO_UTENTE = """
Il destinatario è uno studente del Dipartimento di Economia. 
Interessi: Mobilità internazionale, programmi UniGreen, BIP (Blended Intensive Programs), Erasmus+.
Obiettivo: Trovare opportunità di studio o semplicemente di esperienza, ma non lavoro, che offrano borse di studio o rimborsi spese (funding/grants).
Filtro: Scarta bandi riservati esclusivamente ad Area Giuridica, Medicina o Lettere, a meno che non siano aperti a tutti.
"""

def analizza_bando_con_ai(url):
    if not GEMINI_KEY: return "Non specificata", "Non specificato", "No"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        testo_pagina = soup.get_text(separator=' ', strip=True)[:5000] # Aumentato a 5000 caratteri
        
        # 🧠 PROMPT EVOLUTO CON SKILLS E CONTESTO
        prompt = f"""
        {PROFILO_UTENTE}
        
        Analizza il seguente testo di un bando universitario e fornisci le informazioni richieste.
        TESTO DA ANALIZZARE: {testo_pagina}

        REGOLE DI RISPOSTA:
        Rispondi ESCLUSIVAMENTE con questo schema, senza commenti extra:
        Scadenza: [Data esatta o 'Scaduto' o 'Non indicata']
        Periodo/Destinazione: [Luogo e durata dell'esperienza]
        Borsa di Studio: [SI/NO - Indica SI se sono menzionati finanziamenti, rimborsi, grants o esenzioni tasse]
        Compatibilità: [Voto da 1 a 10 per uno studente di Economia]
        """

        risposta = model.generate_content(prompt)
        linee = risposta.text.strip().split('\n')
        
        # Estrazione pulita dei dati
        scadenza = linee[0].split(":")[1].strip() if len(linee) > 0 else "N.D."
        periodo = linee[1].split(":")[1].strip() if len(linee) > 1 else "N.D."
        ha_borsa = "SI" in linee[2].upper() if len(linee) > 2 else False
        voto = linee[3].split(":")[1].strip() if len(linee) > 3 else "5"
        
        return scadenza, periodo, ha_borsa, voto
    except Exception:
        return "Da verificare", "Da verificare", False, "N.D."

def run_unigreen_worker(memoria):
    try:
        for nome_fonte, url in URLS.items():
            response = requests.get(url, timeout=15)
            soup = BeautifulSoup(response.text, "html.parser")
            
            for link_tag in soup.find_all('a', href=True):
                testo_link = link_tag.text.strip()
                href = link_tag['href']
                
                # Filtro preliminare per non sprecare chiamate AI
                if len(testo_link) < 10: continue
                
                id_bando = "uni_" + generate_hash(href)
                if id_bando not in memoria:
                    
                    # 🚀 L'AI ORA USA IL TUO PROFILO
                    scadenza, periodo, ha_borsa, voto = analizza_bando_con_ai(href)
                    
                    # Se il voto di compatibilità è troppo basso, lo ignoriamo (Filtro intelligente)
                    try:
                        if int(voto.split("/")[0]) < 6: continue 
                    except: pass

                    etichetta_soldi = "💰 **BORSA DI STUDIO RILEVATA**\n" if ha_borsa else ""
                    
                    testo_messaggio = (
                        f"🎓 **OPPORTUNITÀ SELEZIONATA** (Rating: {voto}/10)\n\n"
                        f"{etichetta_soldi}"
                        f"📌 *{testo_link}*\n\n"
                        f"⏳ **Scadenza:** `{scadenza}`\n"
                        f"🌍 **Svolgimento:** `{periodo}`\n"
                        f"🏫 **Fonte:** {nome_fonte}"
                    )
                    
                    bottoni = [[{"text": "🌐 Apri Bando", "url": href}],
                               [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]]
                    
                    invia_telegram(testo_messaggio, bottoni)
                    
                    memoria[id_bando] = {
                        "stato": "nuovo",
                        "titolo": testo_link,
                        "url": href,
                        "tipo": "universita",
                        "funding": ha_borsa,
                        "scadenza": scadenza,
                        "periodo": periodo,
                        "voto": voto,
                        "data_rilevazione": datetime.now().strftime("%d/%m/%Y %H:%M")
                    }
        update_health("unigreen_worker", "ok")
    except Exception as e:
        update_health("unigreen_worker", f"error: {str(e)}")
    return memoria
