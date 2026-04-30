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
    return memoria
