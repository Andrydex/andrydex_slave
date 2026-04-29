import json
import os

MEMORY_PATH = "data/memoria.json"


def load_memory():

    if not os.path.exists(MEMORY_PATH):

        return {"sent_games": []}

    with open(MEMORY_PATH, "r") as file:

        return json.load(file)


def save_memory(memory):

    with open(MEMORY_PATH, "w") as file:

        json.dump(memory, file, indent=2)


def already_sent(memory, title):

    return title in memory["sent_games"]


def mark_as_sent(memory, title):

    memory["sent_games"].append(title)
