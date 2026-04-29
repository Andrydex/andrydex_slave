import json
import os
import requests
import logging

MEMORY_PATH = "data/memoria.json"
GH_TOKEN = os.environ.get("MY_GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")

def load_memory():
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    if not os.path.exists(MEMORY_PATH):
        return {}
    with open(MEMORY_PATH, "r") as file:
        return json.load(file)

def save_memory(memory):
    with open(MEMORY_PATH, "w") as file:
        json.dump(memory, file, indent=4)

def sincronizza_presi(memoria):
    if not GH_TOKEN: return memoria
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        issues = requests.get(f"https://api.github.com/repos/{REPO}/issues?state=open", headers=headers).json()
        for issue in issues:
            titolo_i = issue.get("title", "")
            num = issue.get('number')
            if not num: continue

            if titolo_i.startswith("PRESO:"):
                id_g = titolo_i.replace("PRESO:", "").strip()
                if id_g in memoria: memoria[id_g]["stato"] = "preso"
            elif titolo_i.startswith("HO_BASE:"):
                nome_base = titolo_i.replace("HO_BASE:", "").strip().lower()
                memoria[f"base_{nome_base}"] = {"stato": "preso", "titolo": nome_base}
            elif titolo_i.startswith("NO_BASE:"):
                id_g = titolo_i.replace("NO_BASE:", "").strip()
                memoria[id_g] = {"stato": "ignorato"}
            
            # Chiude l'issue in automatico
            requests.patch(f"https://api.github.com/repos/{REPO}/issues/{num}", headers=headers, json={"state": "closed"})
    except Exception as e:
        logging.error(f"Errore sincronizzazione Issues: {e}")
    return memoria
