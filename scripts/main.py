import logging
from datetime import datetime
from memory_manager import load_memory, save_memory, sincronizza_presi
from gaming_worker import run_gaming_worker
from cheapshark_worker import run_cheapshark_worker
from unigreen_worker import run_unigreen_worker
from startup_worker import run_startup_worker
from telegram_sender import invia_telegram

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.info("🤖 Avvio sistema multi-bot...")
    
    memoria = load_memory()
    memoria = sincronizza_presi(memoria)

    # 📅 Divisorio giornaliero
    oggi = datetime.now().strftime("%d/%m/%Y")
    invia_telegram(f"━━━━━━━━━━━━━━━━━━\n🗓 **LOG: {oggi}**\n━━━━━━━━━━━━━━━━━━")

    # 🚀 ESECUZIONE LAVORATORI
    memoria = run_gaming_worker(memoria)
    memoria = run_cheapshark_worker(memoria)
    memoria = run_unigreen_worker(memoria)
    memoria = run_startup_worker(memoria)
    
    save_memory(memoria)
    logging.info("🏁 Tutti i processi completati.")

if __name__ == "__main__":
    main()
