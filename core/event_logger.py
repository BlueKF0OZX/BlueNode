from datetime import datetime

import os
from runtime_io import append_bounded


LOG_FILE = "/opt/nodesmart/logs/events.log"


def emit(event, message=""):

    timestamp = datetime.now().isoformat(timespec="seconds")

    event = str(event).replace("\n", " ").replace("\r", " ")[:128]
    message = str(message).replace("\n", " ").replace("\r", " ")[:8192]
    line = f"{timestamp} | {event} | {message}\n"


    try:
        append_bounded(LOG_FILE, line)
    except (OSError, ValueError):
        print('BlueNode event log write failed', flush=True)



if __name__ == "__main__":

    emit("NODESMART.STARTED", "BlueNode event system test")
