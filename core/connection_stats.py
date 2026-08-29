
#!/usr/bin/env python3



import json

from datetime import datetime, timezone, time

from pathlib import Path





HISTORY_FILE = Path("/opt/nodesmart/history/connections.jsonl")

ALLSTAR_STATE_FILE = Path("/opt/nodesmart/events/allstar_state.json")





def load_history():

    records = []



    if not HISTORY_FILE.exists():

        return records



    with HISTORY_FILE.open() as file:

        for line in file:

            line = line.strip()



            if not line:

                continue



            try:

                records.append(json.loads(line))

            except json.JSONDecodeError:

                continue



    return records





def load_active_connections():

    try:

        with ALLSTAR_STATE_FILE.open() as file:

            data = json.load(file)



        return data.get("connected_since", {})



    except (OSError, json.JSONDecodeError):

        return {}





def parse_datetime(value):

    if not value:

        return None



    try:

        dt = datetime.fromisoformat(value)

    except (ValueError, TypeError):

        return None



    if dt.tzinfo is None:

        dt = dt.replace(tzinfo=timezone.utc)



    return dt.astimezone(timezone.utc)





def overlap_seconds(started, ended, window_start, window_end):

    start = max(started, window_start)

    end = min(ended, window_end)



    if end <= start:

        return 0



    return int((end - start).total_seconds())





def summarize_connections():

    records = load_history()

    active_connections = load_active_connections()



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
