import logging
from memory_manager import load_memory, save_memory, sincronizza_presi
from gaming_worker import run_gaming_worker
from steam_worker import run_steam_worker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.info("🤖 Avvio del sistema principale...")
    
    # 1. Carica e aggiorna la memoria
    memoria = load_memory()
    memoria = sincronizza_presi(memoria)

    # 2. Lancia i lavoratori
    memoria = run_gaming_worker(memoria)
    memoria = run_steam_worker(memoria)
    
    # 3. Salva e spegni
    save_memory(memoria)
    logging.info("🏁 Tutti i processi completati con successo.")

if __name__ == "__main__":
    main()
