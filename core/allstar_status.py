
import subprocess

import json

import os



from datetime import datetime, timezone

from event_logger import emit
from config import load_config




CONFIG = load_config()
NODE = str(CONFIG["node"])
NODE_NAMES = {str(k): v for k, v in CONFIG.get("friendly_nodes", {}).items()}

STATE_FILE = "/opt/nodesmart/events/allstar_state.json"

CONNECTION_HISTORY_FILE = "/opt/nodesmart/history/connections.jsonl"








def friendly_name(node):

    name = NODE_NAMES.get(node)



    if name:

        return f"{name} ({node})"



    return f"Node {node}"





def get_links():

    result = subprocess.run(

        ["sudo", "-n", "asterisk", "-rx", f"rpt lstats {NODE}"],

        capture_output=True,

        text=True

    )



    links = set()



    for line in result.stdout.splitlines()[2:]:

        parts = line.split()



        if parts and parts[0].isdigit():

            links.add(parts[0])



    return links





def load_state():

    if not os.path.exists(STATE_FILE):

        return {

            "links": [],

            "connected_since": {}

        }



    try:

        with open(STATE_FILE, "r") as f:

            data = json.load(f)



        return {

            "links": data.get("links", []),

            "connected_since": data.get("connected_since", {})

        }



    except (OSError, json.JSONDecodeError):

        return {

            "links": [],

            "connected_since": {}

        }





def save_state(links, connected_since):

    with open(STATE_FILE, "w") as f:

        json.dump(

            {

                "links": sorted(links),

                "connected_since": connected_since

            },

            f,

            indent=2

        )





def format_duration(start_time, end_time):

    try:

        start = datetime.fromisoformat(start_time)

        seconds = int((end_time - start).total_seconds())



        hours, remainder = divmod(seconds, 3600)

        minutes, seconds = divmod(remainder, 60)



        if hours:

            return f"{hours}h {minutes}m {seconds}s"



        if minutes:

            return f"{minutes}m {seconds}s"



        return f"{seconds}s"



    except (TypeError, ValueError):

        return None







def save_connection_history(node, started, ended):

    """Append a completed AllStar connection session to history."""



    if not started:

        return



    try:

        started_dt = datetime.fromisoformat(started)

        duration_seconds = max(

            0,

            int((ended - started_dt).total_seconds())

        )

    except (ValueError, TypeError):

        return



    os.makedirs(

        os.path.dirname(CONNECTION_HISTORY_FILE),

        exist_ok=True

    )



    record = {

        "node": str(node),

        "name": NODE_NAMES.get(str(node), ""),

        "connected_at": started_dt.isoformat(),

        "disconnected_at": ended.isoformat(),

        "duration_seconds": duration_seconds,

    }



    with open(CONNECTION_HISTORY_FILE, "a") as file:

        file.write(json.dumps(record) + "\n")





def check_changes():

    current = get_links()



    state = load_state()

    previous = set(state["links"])

    connected_since = state["connected_since"]



    now = datetime.now(timezone.utc)



    connected = current - previous

    disconnected = previous - current



    for node in connected:

        connected_since[node] = now.isoformat()



        emit(

            "NODE.CONNECTED",

            f"{friendly_name(node)} connected"

        )



    for node in disconnected:

        started = connected_since.pop(node, None)

        duration = format_duration(started, now)



        if duration:

            message = (

                f"{friendly_name(node)} disconnected "

                f"after {duration}"

            )

        else:

            message = f"{friendly_name(node)} disconnected"



        emit("NODE.DISCONNECTED", message)

        save_connection_history(node, started, now)



    # If NodeSmart restarted while a link was already active,

    # begin tracking it from this monitor session.

    for node in current:

        connected_since.setdefault(node, now.isoformat())



    save_state(current, connected_since)





if __name__ == "__main__":

    check_changes()
