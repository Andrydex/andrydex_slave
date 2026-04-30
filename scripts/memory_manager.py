import json
import os
from datetime import datetime, timedelta

MEMORIA_PATH = 'data/memoria.json'

def load_memory():
    if os.path.exists(MEMORIA_PATH):
        with open(MEMORIA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_memory(memoria):
    # --- 🧹 PULIZIA AUTOMATICA (TTL) ---
    limite_giochi = datetime.now() - timedelta(days=30)
    limite_bandi = datetime.now() - timedelta(days=60)
    
    nuova_memoria = {}
    for k, v in memoria.items():
        data_rif = v.get("data_rilevazione", "01/01/2000")
        try:
            data_dt = datetime.strptime(data_rif.split()[0], "%d/%m/%Y")
        except:
            data_dt = datetime.now()

        # Teniamo i bandi per 60 giorni e i giochi per 30
        if v.get("tipo") == "universita":
            if data_dt > limite_bandi: nuova_memoria[k] = v
        else:
            if data_dt > limite_giochi: nuova_memoria[k] = v
    
    with open(MEMORIA_PATH, 'w', encoding='utf-8') as f:
        json.dump(nuova_memoria, f, indent=4, ensure_ascii=False)

def sincronizza_presi(memoria):
    # Mantieni questa funzione se la usi per sincronizzare lo stato tra bot diversi
    return memoria
