import json
from datetime import datetime

HEALTH_PATH = "data/health.json"


def update_health(worker_name, status):

    data = {}

    try:

        with open(HEALTH_PATH, "r") as file:

            data = json.load(file)

    except:

        pass

    data[worker_name] = {
        "status": status,
        "last_check": datetime.utcnow().isoformat()
    }

    with open(HEALTH_PATH, "w") as file:

        json.dump(data, file, indent=2)
