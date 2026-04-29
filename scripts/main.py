from steam_worker import fetch_free_games
from telegram_sender import send_message

from memory_manager import (
    load_memory,
    save_memory,
    already_sent,
    mark_as_sent
)

from health_check import update_health

memory = load_memory()

try:

    games = fetch_free_games()

    update_health("steam_worker", "ok")

    for game in games:

        if not already_sent(memory, game["title"]):

            message = (
                f"🎮 Nuovo gioco gratis:\n\n"
                f"{game['title']}\n"
                f"{game['url']}"
            )

            send_message(message)

            mark_as_sent(memory, game["title"])

    save_memory(memory)

except Exception as e:

    update_health("steam_worker", f"error: {str(e)}")

    raise
