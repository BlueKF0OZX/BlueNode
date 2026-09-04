from datetime import datetime

import os


LOG_FILE = "/opt/nodesmart/logs/events.log"


def emit(event, message=""):

    timestamp = datetime.now().isoformat(timespec="seconds")

    line = f"{timestamp} | {event} | {message}\n"


    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


    with open(LOG_FILE, "a") as f:

        f.write(line)


    print(line.strip())



if __name__ == "__main__":

    emit("NODESMART.STARTED", "BlueNode event system test")
