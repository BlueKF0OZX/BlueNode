
#!/usr/bin/env python3



import json
import connection_state
from runtime_io import tail_lines, HISTORY_BYTES

from datetime import datetime, timezone, time

from pathlib import Path





HISTORY_FILE = Path("/opt/nodesmart/history/connections.jsonl")

ALLSTAR_STATE_FILE = Path("/opt/nodesmart/events/allstar_state.json")





def load_history():
    records = []
    for line in tail_lines(HISTORY_FILE, HISTORY_BYTES, backups=2):
        try:
            record = json.loads(line)
            started = parse_datetime(record.get('connected_at')) if isinstance(record, dict) else None
            ended = parse_datetime(record.get('disconnected_at')) if isinstance(record, dict) else None
            if (started is not None and ended is not None and started <= ended <= datetime.now(timezone.utc)
                    and connection_state.numeric(record.get('node'))
                    and isinstance(record.get('name', ''), str)):
                records.append(record)
        except (ValueError, TypeError, RecursionError):
            continue
    return records


def load_active_connections():
    return connection_state.load(ALLSTAR_STATE_FILE)['connected_since']


def parse_datetime(value):
    return connection_state.timestamp(value)


def overlap_seconds(started, ended, window_start, window_end):

    start = max(started, window_start)

    end = min(ended, window_end)



    if end <= start:

        return 0



    return int((end - start).total_seconds())





def summarize_connections():

    records = load_history()

    observed = connection_state.load(ALLSTAR_STATE_FILE)
    active_connections = observed['connected_since']



    now = datetime.now(timezone.utc)



    today_start = datetime.combine(

        now.date(),

        time.min,

        tzinfo=timezone.utc

    )



    today_end = now



    completed_sessions_today = []

    completed_seconds_today = 0



    for record in records:

        started = parse_datetime(record.get("connected_at"))

        ended = parse_datetime(record.get("disconnected_at"))



        if not started or not ended:

            continue



        seconds_today = overlap_seconds(

            started,

            ended,

            today_start,

            today_end

        )



        if seconds_today <= 0:

            continue



        session = dict(record)

        session["seconds_today"] = seconds_today



        completed_sessions_today.append(session)

        completed_seconds_today += seconds_today



    active_sessions = []

    active_seconds_today = 0



    for node, started_value in active_connections.items():

        started = parse_datetime(started_value)



        if not started:

            continue



        seconds_today = overlap_seconds(

            started,

            now,

            today_start,

            today_end

        )



        active_seconds_today += seconds_today



        active_sessions.append({

            "node": str(node),

            "connected_at": started.isoformat(),

            "seconds_today": seconds_today,

            "duration_seconds": max(

                0,

                int((now - started).total_seconds())

            ),

        })



    total_seconds_today = (

        completed_seconds_today +

        active_seconds_today

    )



    last_session = records[-1] if records else None



    longest_session_today = None



    candidates = []



    for session in completed_sessions_today:

        candidates.append({

            "node": session.get("node"),

            "name": session.get("name"),

            "duration_seconds": session.get("seconds_today", 0),

            "active": False,

        })



    for session in active_sessions:

        candidates.append({

            "node": session.get("node"),

            "name": None,

            "duration_seconds": session.get("seconds_today", 0),

            "active": True,

        })



    if candidates:

        longest_session_today = max(

            candidates,

            key=lambda item: item.get("duration_seconds", 0)

        )



    recent_sessions = records[-5:]

    recent_sessions.reverse()



    return {

        "state_available": observed["state_available"],

        "connections_today":

            len(completed_sessions_today) + len(active_sessions),



        "completed_connections_today":

            len(completed_sessions_today),



        "connected_seconds_today":

            total_seconds_today,



        "completed_connected_seconds_today":

            completed_seconds_today,



        "active_connections":

            len(active_sessions),



        "active_connected_seconds":

            active_seconds_today,



        "last_session":

            last_session,



        "longest_session_today":

            longest_session_today,



        "recent_sessions":

            recent_sessions,

    }





if __name__ == "__main__":

    print(

        json.dumps(

            summarize_connections(),

            indent=2

        )

    )
