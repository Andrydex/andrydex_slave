import json
import os
from datetime import datetime, timedelta

MEMORIA_PATH = 'data/memoria.json'

def load_memory():
    if os.path.exists(MEMORIA_PATH):
        try:
            with open(MEMORIA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except: return {}
    return {}

def save_memory(memoria):
    limite_giochi = datetime.now() - timedelta(days=30)
    limite_bandi = datetime.now() - timedelta(days=60)
    
    nuova_memoria = {}
    for k, v in memoria.items():
        # 🛡️ FIX: Controlliamo che v sia un dizionario
        if not isinstance(v, dict): continue 

        # Preserva metadati interni
        if k.startswith("__"): 
            nuova_memoria[k] = v
            continue
        
        data_rif = v.get("data_rilevazione", "01/01/2000")
        try:
            data_dt = datetime.strptime(data_rif.split()[0], "%d/%m/%Y")
        except:
            data_dt = datetime.now()

        if v.get("tipo") == "universita":
            if data_dt > limite_bandi: nuova_memoria[k] = v
        else:
            if data_dt > limite_giochi: nuova_memoria[k] = v
    
    with open(MEMORIA_PATH, 'w', encoding='utf-8') as f:
        json.dump(nuova_memoria, f, indent=4, ensure_ascii=False)

def sincronizza_presi(memoria):
    import os, requests, logging
    token = os.environ.get("MY_GITHUB_TOKEN")
    repo = "Andrydex/andrydex_slave"
    if not token: return memoria

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        issues = requests.get(
            f"https://api.github.com/repos/{repo}/issues?state=open&per_page=50",
            headers=headers, timeout=10
        ).json()

        for issue in issues:
            if not isinstance(issue, dict): continue
            titolo = issue.get("title", "")
            issue_number = issue.get("number")

            if ":" not in titolo: continue
            azione, item_id = titolo.split(":", 1)
            azione = azione.strip().upper()
            item_id = item_id.strip()

            aggiornato = False

            if azione == "PRESO" and item_id in memoria:
                memoria[item_id]["stato"] = "preso"
                aggiornato = True

            elif azione == "HO_BASE":
                nome_base = f"base_{item_id.lower()}"
                memoria[nome_base] = {"stato": "confermato"}
                aggiornato = True

            elif azione == "NO_BASE" and item_id in memoria:
                memoria[item_id]["stato"] = "ignorato"
                aggiornato = True

            elif azione == "PARTECIPO" and item_id in memoria:
                memoria[item_id]["stato"] = "partecipo"
                aggiornato = True

            elif azione == "IGNORA_BANDO" and item_id in memoria:
                memoria[item_id]["stato"] = "ignorato"
                aggiornato = True
            elif azione == "IGNORA" and item_id in memoria:
                memoria[item_id]["stato"] = "ignorato"
                aggiornato = True

            # Chiude la Issue dopo averla processata
            if aggiornato:
                requests.patch(
                    f"https://api.github.com/repos/{repo}/issues/{issue_number}",
                    headers=headers,
                    json={"state": "closed"},
                    timeout=10
                )
                logging.info(f"✅ Sincronizzato: {titolo}")

    except Exception as e:
        logging.warning(f"Errore sincronizza_presi: {e}")

    return memoria
