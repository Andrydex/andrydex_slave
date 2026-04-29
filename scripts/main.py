import logging
from datetime import datetime
from memory_manager import load_memory, save_memory, sincronizza_presi
from gaming_worker import run_gaming_worker
from cheapshark_worker import run_cheapshark_worker
from telegram_sender import invia_telegram # Importiamo il mittente per il divisorio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.info("🤖 Avvio del sistema principale...")
    
    memoria = load_memory()
    memoria = sincronizza_presi(memoria)

    # 📅 MANDA IL DIVISORIO GIORNALIERO (Effetto Agenda)
    oggi = datetime.now().strftime("%d/%m/%Y")
    invia_telegram(f"━━━━━━━━━━━━━━━━━━\n🗓 **AGGIORNAMENTO: {oggi}**\n━━━━━━━━━━━━━━━━━━")

    # LANCIA I DUE LAVORATORI
    memoria = run_gaming_worker(memoria)
    memoria = run_cheapshark_worker(memoria)
    
    save_memory(memoria)
    logging.info("🏁 Tutti i processi completati con successo.")

if __name__ == "__main__":
    main()
