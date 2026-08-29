
#!/usr/bin/env python3



import json

from datetime import datetime, timedelta, timezone

from pathlib import Path





STATE_FILE = Path("/opt/nodesmart/state/system.json")

RECOVERY_FILE = Path("/opt/nodesmart/state/recovery.json")

EVENT_LOG = Path("/opt/nodesmart/logs/events.log")
INTELLIGENCE_FILE = Path("/opt/nodesmart/state/intelligence.json")





def load_json(path):

    try:

        with path.open() as file:

            return json.load(file)

    except (OSError, json.JSONDecodeError):

        return {}





def load_state():

    return load_json(STATE_FILE)





def load_recovery_state():

    return load_json(RECOVERY_FILE)





def friendly_status(value):

    if not value:

        return "unknown"



    return str(value).replace("_", " ").lower()





def format_duration(seconds):

    seconds = max(0, int(seconds or 0))



    hours = seconds // 3600

    minutes = (seconds % 3600) // 60



    if hours and minutes:

        return (

            f"{hours} hour{'s' if hours != 1 else ''} "

            f"{minutes} minute{'s' if minutes != 1 else ''}"

        )



    if hours:

        return f"{hours} hour{'s' if hours != 1 else ''}"



    if minutes:

        return f"{minutes} minute{'s' if minutes != 1 else ''}"



    return "less than a minute"





def format_age(timestamp):

    if not timestamp:

        return None



    try:

        event_time = datetime.fromisoformat(timestamp)

    except (ValueError, TypeError):

        return None



    if event_time.tzinfo is None:

        event_time = event_time.replace(tzinfo=timezone.utc)



    now = datetime.now(timezone.utc)

    seconds = max(

        0,

        int((now - event_time.astimezone(timezone.utc)).total_seconds())

    )



    if seconds < 60:

        return "less than a minute ago"



    minutes = seconds // 60



    if minutes < 60:

        return (

            f"{minutes} minute{'s' if minutes != 1 else ''} ago"

        )



    hours = minutes // 60



    if hours < 24:

        return (

            f"{hours} hour{'s' if hours != 1 else ''} ago"

        )



    days = hours // 24



    return f"{days} day{'s' if days != 1 else ''} ago"





def load_events():

    events = []



    if not EVENT_LOG.exists():

        return events



    local_tz = datetime.now().astimezone().tzinfo



    try:

        with EVENT_LOG.open() as file:

            for line in file:

                parts = [part.strip() for part in line.split("|", 2)]



                if len(parts) != 3:

                    continue



                timestamp, event, message = parts



                try:

                    event_time = datetime.fromisoformat(timestamp)



                    if event_time.tzinfo is None:

                        event_time = event_time.replace(tzinfo=local_tz)



                    event_time = event_time.astimezone(timezone.utc)



                except ValueError:

                    continue



                events.append({

                    "timestamp": event_time,

                    "event": event,

                    "message": message,

                })



    except OSError:

        return []



    return events





def recent_incident_stats():

    events = load_events()



    now = datetime.now(timezone.utc)

    one_hour_ago = now - timedelta(hours=1)

    one_day_ago = now - timedelta(hours=24)



    asterisk_failures_hour = 0

    asterisk_failures_day = 0

    recovery_successes_day = 0

    recovery_failures_day = 0



    last_asterisk_failure = None

    last_recovery_success = None

    last_recovery_failure = None



    for item in events:

        event = item["event"]

        event_time = item["timestamp"]



        if event == "ASTERISK.OFFLINE":

            if event_time >= one_hour_ago:

                asterisk_failures_hour += 1



            if event_time >= one_day_ago:

                asterisk_failures_day += 1



            if (

                last_asterisk_failure is None

                or event_time > last_asterisk_failure

            ):

                last_asterisk_failure = event_time



        if event == "RECOVERY.ASTERISK.FAILED":

            if event_time >= one_day_ago:

                recovery_failures_day += 1



            if (

                last_recovery_failure is None

                or event_time > last_recovery_failure

            ):

                last_recovery_failure = event_time





        if event == "RECOVERY.ASTERISK.SUCCESS":

            if event_time >= one_day_ago:

                recovery_successes_day += 1



            if (

                last_recovery_success is None

                or event_time > last_recovery_success

            ):

                last_recovery_success = event_time



    return {

        "asterisk_failures_hour": asterisk_failures_hour,

        "asterisk_failures_day": asterisk_failures_day,

        "recovery_successes_day": recovery_successes_day,

        "recovery_failures_day": recovery_failures_day,

        "last_asterisk_failure": last_asterisk_failure,

        "last_recovery_success": last_recovery_success,

        "last_recovery_failure": last_recovery_failure,

    }





def save_intelligence(data):

    INTELLIGENCE_FILE.parent.mkdir(parents=True, exist_ok=True)



    with INTELLIGENCE_FILE.open("w") as file:

        json.dump(data, file, indent=2)





def classify_event(event):

    if event.startswith("SYSTEM.FAULT"):

        return "incident"



    if event.startswith("ASTERISK.OFFLINE"):

        return "incident"



    if event.startswith("RECOVERY."):

        return "recovery"



    if event.startswith("HEALTH.") and event.endswith(".CRITICAL"):

        return "incident"



    if event.startswith("HEALTH.") and event.endswith(".WARNING"):

        return "incident"



    return "routine"







def correlate_activity(events):

    """

    Correlate low-level event records into logical incidents and

    recovery operations.



    Multiple events can describe the same underlying problem. For

    example:



        SYSTEM.FAULT

        HEALTH.ASTERISK.CRITICAL

        ASTERISK.OFFLINE



    represent one Asterisk incident, not three separate incidents.



    Likewise:



        RECOVERY.ASTERISK.ATTEMPT

        RECOVERY.ASTERISK.SUCCESS



    represent one recovery operation.

    """



    incidents = []

    recoveries = []



    # Asterisk incidents are anchored by ASTERISK.OFFLINE.

    #

    # SYSTEM.FAULT and HEALTH.ASTERISK.CRITICAL may describe the same

    # outage, so they are not independently counted when an explicit

    # ASTERISK.OFFLINE event exists nearby.

    asterisk_offline_events = [

        item for item in events

        if item["event"] == "ASTERISK.OFFLINE"

    ]



    for item in asterisk_offline_events:

        incidents.append({

            "component": "asterisk",

            "timestamp": item["timestamp"],

            "event": item["event"],

        })



    # Count non-Asterisk health incidents separately. These represent

    # real component conditions that are not merely duplicate records

    # of an Asterisk outage.

    for item in events:

        event = item["event"]



        if not event.startswith("HEALTH."):

            continue



        if not (

            event.endswith(".WARNING")

            or event.endswith(".CRITICAL")

        ):

            continue



        # Asterisk failures are already represented by ASTERISK.OFFLINE.

        if event.startswith("HEALTH.ASTERISK."):

            continue



        incidents.append({

            "component": event,

            "timestamp": item["timestamp"],

            "event": event,

        })



    # Recovery operations are anchored by ATTEMPT. SUCCESS and FAILED

    # describe the outcome of that same operation and should not create

    # additional recovery counts.

    for item in events:

        if item["event"] == "RECOVERY.ASTERISK.ATTEMPT":

            recoveries.append({

                "component": "asterisk",

                "timestamp": item["timestamp"],

                "event": item["event"],

            })



    return {

        "incidents": incidents,

        "recoveries": recoveries,

    }







def build_incident_records(events):

    """

    Build logical incident records from raw NodeSmart events.



    Correlated components:

      - Asterisk offline/recovery/normal

      - Internet offline/online

      - CPU warning/critical/normal

      - Memory warning/critical/normal

      - Disk warning/critical/normal



    Multiple severity changes inside one fault are treated as one incident.

    """



    records = []



    events = sorted(

        events,

        key=lambda item: item["timestamp"]

    )



    # ------------------------------------------------------------

    # Asterisk incidents

    # ------------------------------------------------------------



    offline_events = [

        item for item in events

        if item["event"] == "ASTERISK.OFFLINE"

    ]



    for offline in offline_events:

        start_time = offline["timestamp"]



        record = {

            "component": "asterisk",

            "started_at": start_time.isoformat(),

            "started_state": "offline",

            "highest_state": "critical",

            "recovery_attempted": False,

            "recovery_outcome": None,

            "recovery_at": None,

            "resolved": False,

            "resolved_at": None,

            "duration_seconds": None,

        }



        for item in events:

            event = item["event"]

            event_time = item["timestamp"]



            if event_time < start_time:

                continue



            # A later outage belongs to another incident.

            if (

                event == "ASTERISK.OFFLINE"

                and event_time > start_time

            ):

                break



            if event == "RECOVERY.ASTERISK.ATTEMPT":

                record["recovery_attempted"] = True



            elif event == "RECOVERY.ASTERISK.SUCCESS":

                record["recovery_outcome"] = "success"

                record["recovery_at"] = event_time.isoformat()



            elif event == "RECOVERY.ASTERISK.FAILED":

                record["recovery_outcome"] = "failed"

                record["recovery_at"] = event_time.isoformat()



            elif event == "HEALTH.ASTERISK.NORMAL":

                record["resolved"] = True

                record["resolved_at"] = event_time.isoformat()

                record["duration_seconds"] = int(

                    (event_time - start_time).total_seconds()

                )

                break



        if record["resolved"]:

            duration = record["duration_seconds"]



            if record["recovery_outcome"] == "success":

                record["summary"] = (

                    f"Asterisk went offline and was automatically "

                    f"recovered in {duration} seconds."

                )



            elif record["recovery_outcome"] == "failed":

                record["summary"] = (

                    f"Asterisk went offline. Automatic recovery failed, "

                    f"but service later returned after {duration} seconds."

                )



            else:

                record["summary"] = (

                    f"Asterisk went offline and returned to normal "

                    f"after {duration} seconds."

                )



        else:

            if record["recovery_outcome"] == "failed":

                record["summary"] = (

                    "Asterisk is offline and automatic recovery failed."

                )



            elif record["recovery_attempted"]:

                record["summary"] = (

                    "Asterisk is offline and automatic recovery was attempted."

                )



            else:

                record["summary"] = (

                    "Asterisk is offline and the incident remains unresolved."

                )



        records.append(record)



    # ------------------------------------------------------------

    # Internet incidents

    # ------------------------------------------------------------



    internet_offline_events = [

        item for item in events

        if item["event"] == "INTERNET.OFFLINE"

    ]



    for offline in internet_offline_events:

        start_time = offline["timestamp"]



        record = {

            "component": "internet",

            "started_at": start_time.isoformat(),

            "started_state": "offline",

            "highest_state": "critical",

            "recovery_attempted": False,

            "recovery_outcome": None,

            "recovery_at": None,

            "resolved": False,

            "resolved_at": None,

            "duration_seconds": None,

        }



        for item in events:

            event = item["event"]

            event_time = item["timestamp"]



            if event_time <= start_time:

                continue



            # Another offline transition means the next incident began.

            if event == "INTERNET.OFFLINE":

                break



            if event == "INTERNET.ONLINE":

                record["resolved"] = True

                record["resolved_at"] = event_time.isoformat()

                record["duration_seconds"] = int(

                    (event_time - start_time).total_seconds()

                )

                break



        if record["resolved"]:

            record["summary"] = (

                f"Internet connectivity was lost and restored after "

                f"{record['duration_seconds']} seconds."

            )

        else:

            record["summary"] = (

                "Internet connectivity is offline and the incident "

                "remains unresolved."

            )



        records.append(record)



    # ------------------------------------------------------------

    # CPU / memory / disk health incidents

    # ------------------------------------------------------------



    component_labels = {

        "cpu": "CPU",

        "memory": "Memory",

        "disk": "Disk",

    }



    severity_rank = {

        "warning": 1,

        "critical": 2,

    }



    for component, label in component_labels.items():

        active = None



        prefix = f"HEALTH.{component.upper()}."



        for item in events:

            event = item["event"]



            if not event.startswith(prefix):

                continue



            state = event[len(prefix):].lower()

            event_time = item["timestamp"]



            if state in ("warning", "critical"):

                if active is None:

                    active = {

                        "component": component,

                        "started_at": event_time.isoformat(),

                        "started_state": state,

                        "highest_state": state,

                        "recovery_attempted": False,

                        "recovery_outcome": None,

                        "recovery_at": None,

                        "resolved": False,

                        "resolved_at": None,

                        "duration_seconds": None,

                    }



                elif (

                    severity_rank.get(state, 0)

                    > severity_rank.get(

                        active["highest_state"],

                        0

                    )

                ):

                    active["highest_state"] = state



            elif state == "normal" and active is not None:

                start_time = datetime.fromisoformat(

                    active["started_at"]

                )



                active["resolved"] = True

                active["resolved_at"] = event_time.isoformat()

                active["duration_seconds"] = int(

                    (event_time - start_time).total_seconds()

                )



                highest = active["highest_state"].upper()



                active["summary"] = (

                    f"{label} entered {highest} state and returned "

                    f"to normal after "

                    f"{active['duration_seconds']} seconds."

                )



                records.append(active)

                active = None



        # If the log ends while the component is still abnormal,

        # retain it as an unresolved incident.

        if active is not None:

            highest = active["highest_state"].upper()



            active["summary"] = (

                f"{label} remains in {highest} state and the incident "

                f"is unresolved."

            )



            records.append(active)



    records.sort(

        key=lambda record: record["started_at"]

    )



    return records





def recent_activity_stats():

    events = load_events()



    now = datetime.now(timezone.utc)

    one_day_ago = now - timedelta(hours=24)



    recent = [

        item for item in events

        if item["timestamp"] >= one_day_ago

    ]



    connections = sum(

        1 for item in recent

        if item["event"] == "NODE.CONNECTED"

    )



    asterisk_failures = sum(

        1 for item in recent

        if item["event"] == "ASTERISK.OFFLINE"

    )



    recovery_attempts = sum(

        1 for item in recent

        if item["event"] == "RECOVERY.ASTERISK.ATTEMPT"

    )



    recovery_successes = sum(

        1 for item in recent

        if item["event"] == "RECOVERY.ASTERISK.SUCCESS"

    )



    recovery_failures = sum(

        1 for item in recent

        if item["event"] == "RECOVERY.ASTERISK.FAILED"

    )



    health_changes = sum(

        1 for item in recent

        if item["event"].startswith("HEALTH.")

        or item["event"].startswith("SYSTEM.")

    )



    control_actions = sum(

        1 for item in recent

        if item["event"].startswith("CONTROL.")

    )



    latest = recent[-1] if recent else None



    # Use the structured incident engine as the single source
    # of truth for logical incidents and recovery operations.
    incident_records = build_incident_records(recent)

    incidents = len(incident_records)

    recoveries = sum(
        1 for record in incident_records
        if record.get("recovery_attempted")
    )

    # Routine events remain a raw event count. These are ordinary

    # timeline records rather than correlated incidents/recoveries.

    routine_events = sum(

        1 for item in recent

        if classify_event(item["event"]) == "routine"

    )



    return {

        "events_24h": len(recent),

        "incidents_24h": incidents,

        "recoveries_24h": recoveries,

        "routine_events_24h": routine_events,

        "connections_24h": connections,

        "asterisk_failures_24h": asterisk_failures,

        "recovery_attempts_24h": recovery_attempts,

        "recovery_successes_24h": recovery_successes,

        "recovery_failures_24h": recovery_failures,

        "health_changes_24h": health_changes,

        "control_actions_24h": control_actions,

        "latest_event": latest["event"] if latest else None,

        "latest_message": latest["message"] if latest else None,

    }





def build_recommendation(

    level,

    attention_required,

    reasons,

    recovery_failures,

    unresolved_incidents=None,

):

    unresolved_incidents = unresolved_incidents or []



    if unresolved_incidents:

        critical = [

            record for record in unresolved_incidents

            if record.get("highest_state") == "critical"

            or record.get("started_state") == "offline"

        ]



        affected = critical if critical else unresolved_incidents



        summaries = [

            record.get("summary")

            for record in affected

            if record.get("summary")

        ]



        if len(summaries) == 1:

            message = summaries[0]



        elif summaries:

            message = (

                "Multiple active incidents require attention: "

                + " ".join(summaries)

            )



        else:

            components = [

                str(record.get("component", "system")).upper()

                for record in affected

            ]



            message = (

                "Active unresolved incident affecting: "

                + ", ".join(components)

                + "."

            )



        return {

            "action_required": True,

            "priority": "critical" if critical else "warning",

            "message": message,

        }



    if recovery_failures > 0:

        return {

            "action_required": True,

            "priority": "critical",

            "message": (

                "Manual intervention is recommended because "

                "automatic recovery failed."

            ),

        }



    if level == "critical":

        return {

            "action_required": True,

            "priority": "critical",

            "message": "Manual intervention is recommended.",

        }



    if level == "warning":

        if len(reasons) > 1:

            components = []



            for reason in reasons:

                reason_text = str(reason)



                if reason_text.startswith("CPU temperature"):

                    components.append("CPU temperature")

                elif reason_text.startswith("Memory usage"):

                    components.append("memory usage")

                elif reason_text.startswith("Disk usage"):

                    components.append("disk usage")

                elif reason_text.startswith("Internet"):

                    components.append("internet connectivity")

                elif reason_text.startswith("Asterisk"):

                    components.append("Asterisk")

                else:

                    components.append(reason_text)



            return {

                "action_required": attention_required,

                "priority": "warning",

                "message": (

                    "Multiple system conditions require attention: "

                    + ", ".join(components)

                    + "."

                ),

            }



        if reasons:

            return {

                "action_required": attention_required,

                "priority": "warning",

                "message": (

                    "Monitor the affected component and investigate "

                    "if the condition persists."

                ),

            }



        return {

            "action_required": attention_required,

            "priority": "warning",

            "message": (

                "The node remains operational, but the condition "

                "should be monitored."

            ),

        }



    return {

        "action_required": False,

        "priority": "normal",

        "message": "No action is required.",

    }





def build_intelligence(state=None):

    if state is None:

        state = load_state()



    if not state:

        return {

            "level": "unknown",

            "attention_required": True,

            "recent_incidents": 0,

            "asterisk_failures_1h": 0,

            "asterisk_failures_24h": 0,

            "recovery_successes_24h": 0,

            "summary": "NodeSmart system state is unavailable.",

        }



    incident_stats = recent_incident_stats()



    status = friendly_status(state.get("status"))

    reasons = list(state.get("health_reasons", []))



    failures_hour = incident_stats["asterisk_failures_hour"]

    failures_day = incident_stats["asterisk_failures_day"]

    recoveries_day = incident_stats["recovery_successes_day"]

    recovery_failures_day = incident_stats["recovery_failures_day"]



    repeated_failure_warning = failures_day >= 2

    repeated_failure_critical = failures_day >= 3



    # Build structured incidents before deciding intelligence level.

    incident_records = build_incident_records(load_events())



    unresolved_incidents = [

        record for record in incident_records

        if not record.get("resolved", False)

    ]



    unresolved_critical = any(

        record.get("highest_state") == "critical"

        or record.get("started_state") == "offline"

        for record in unresolved_incidents

    )



    unresolved_warning = any(

        record.get("highest_state") == "warning"

        for record in unresolved_incidents

    )



    # Add unresolved incident summaries to the issue list so the

    # dashboard can explain active problems directly.

    for record in unresolved_incidents:

        summary = record.get("summary")



        if summary and summary not in reasons:

            reasons.append(summary)



    if unresolved_critical:

        level = "critical"

        attention_required = True



    elif status == "fault":

        level = "critical"

        attention_required = True



    elif recovery_failures_day > 0:

        level = "critical"

        attention_required = True



    elif repeated_failure_critical:

        level = "critical"

        attention_required = True



    elif unresolved_warning:

        level = "warning"

        attention_required = True



    elif status == "degraded":

        level = "warning"

        attention_required = True



    elif failures_hour >= 3:

        level = "warning"

        attention_required = True



    elif failures_hour == 2:

        level = "warning"

        attention_required = False



    else:

        level = "normal"

        attention_required = False



    recent_activity = recent_activity_stats()



    # Keep only the most recent structured incidents in the

    # intelligence state. The raw event log remains the full history.

    incident_records = incident_records[-20:]



    intelligence = {

        "level": level,

        "attention_required": attention_required,

        "recent_incidents": recent_activity["incidents_24h"],

        "asterisk_failures_1h": failures_hour,

        "asterisk_failures_24h": failures_day,

        "recovery_successes_24h": recoveries_day,

        "recovery_failures_24h": recovery_failures_day,

        "repeated_failure_warning": repeated_failure_warning,

        "repeated_failure_critical": repeated_failure_critical,

        "unresolved_issues": reasons,

        "component_health": dict(state.get("health", {})),

        "recent_activity": recent_activity,

        "incidents": incident_records,

    }



    intelligence["recommendation"] = build_recommendation(

        level,

        attention_required,

        reasons,

        recovery_failures_day,

        unresolved_incidents,

    )



    intelligence["summary"] = build_summary(state)



    save_intelligence(intelligence)

    return intelligence





def build_summary(state=None):

    if state is None:

        state = load_state()



    if not state:

        return "NodeSmart system state is unavailable."



    recovery_state = load_recovery_state()

    incident_stats = recent_incident_stats()



    node = state.get("node", "Unknown node")

    status = friendly_status(state.get("status"))



    asterisk = friendly_status(state.get("asterisk"))

    internet = friendly_status(state.get("internet"))

    skywarn = friendly_status(state.get("skywarn"))



    connected_nodes = state.get("connected_nodes", [])

    friendly_nodes = state.get("friendly_nodes", {})

    reasons = state.get("health_reasons", [])



    connection_stats = state.get("connection_stats", {})



    connections_today = int(

        connection_stats.get("connections_today", 0) or 0

    )



    connected_seconds_today = int(

        connection_stats.get("connected_seconds_today", 0) or 0

    )



    parts = []



    # Overall condition

    if status == "healthy":

        parts.append(f"{node} is healthy.")

    elif status == "degraded":

        parts.append(f"{node} is degraded.")

    elif status == "fault":

        parts.append(f"{node} has a fault.")

    else:

        parts.append(f"{node} status is {status}.")



    # Core services

    parts.append(

        f"Asterisk is {asterisk} and internet is {internet}."

    )



    parts.append(

        f"SkywarnPlus is {skywarn}."

    )



    # Current connections

    if connected_nodes:

        names = []



        for connected_node in connected_nodes:

            connected_node = str(connected_node)



            name = friendly_nodes.get(

                connected_node,

                f"node {connected_node}"

            )



            names.append(name)



        if len(names) == 1:

            parts.append(

                f"Currently connected to {names[0]}."

            )

        else:

            parts.append(

                "Currently connected to " + ", ".join(names) + "."

            )

    else:

        parts.append("No nodes are currently connected.")



    # Today's connection activity

    if connections_today > 0:

        duration = format_duration(connected_seconds_today)



        if connections_today == 1:

            parts.append(

                f"There has been 1 connection today for {duration}."

            )

        else:

            parts.append(

                f"There have been {connections_today} connections today "

                f"for a combined {duration}."

            )



    # Recent Asterisk incident intelligence

    failures_hour = incident_stats["asterisk_failures_hour"]

    failures_day = incident_stats["asterisk_failures_day"]



    if failures_hour >= 3:

        parts.append(

            f"Asterisk has gone offline {failures_hour} times "

            f"during the past hour. Continued instability "

            f"should be investigated."

        )



    elif failures_hour == 2:

        parts.append(

            "Asterisk has gone offline twice during the past hour. "

            "The node is currently operational, but stability "

            "should be watched."

        )



    elif failures_hour == 1 and asterisk == "online":

        parts.append(

            "Asterisk experienced one recent failure and is "

            "currently operational."

        )



    elif failures_day > 0 and asterisk == "online":

        parts.append(

            f"Asterisk experienced {failures_day} "

            f"failure{'s' if failures_day != 1 else ''} "

            f"during the past 24 hours."

        )



    # Most recent recovery

    last_recovery = recovery_state.get("last_recovery")



    if last_recovery:

        recovery_status = friendly_status(

            last_recovery.get("status")

        )



        component = str(

            last_recovery.get("component", "system")

        ).capitalize()



        age = format_age(

            last_recovery.get("timestamp")

        )



        if recovery_status == "success":

            if age:

                parts.append(

                    f"Automatic recovery for {component} "

                    f"succeeded {age}."

                )

            else:

                parts.append(

                    f"The most recent automatic recovery for "

                    f"{component} was successful."

                )



        elif recovery_status == "failed":

            if age:

                parts.append(

                    f"Automatic recovery for {component} "

                    f"failed {age}."

                )

            else:

                parts.append(

                    f"The most recent automatic recovery for "

                    f"{component} failed."

                )



        elif recovery_status == "cancelled":

            parts.append(

                f"The most recent automatic recovery for "

                f"{component} was cancelled because recovery "

                f"was no longer required."

            )



    # Recovery reliability

    recovery_failures_day = incident_stats["recovery_failures_day"]



    repeated_failure_warning = failures_day >= 2

    repeated_failure_critical = failures_day >= 3



    if recovery_failures_day > 0:

        parts.append(

            f"Automatic recovery has failed "

            f"{recovery_failures_day} time"

            f"{'s' if recovery_failures_day != 1 else ''} "

            f"during the past 24 hours. Manual investigation is recommended."

        )



    elif repeated_failure_critical:

        parts.append(

            f"Asterisk has failed {failures_day} times "

            f"during the past 24 hours. This is a recurring "

            f"failure pattern and should be investigated."

        )



    elif repeated_failure_warning:

        parts.append(

            f"Asterisk has failed {failures_day} times "

            f"during the past 24 hours. Continued failures may "

            f"indicate an underlying problem."

        )



    # Current problems / recommendation

    if reasons:

        parts.append(

            "Current issue: "

            + "; ".join(str(reason) for reason in reasons)

            + "."

        )



    elif status == "healthy" and failures_hour < 2:

        parts.append("No action is required.")



    return " ".join(parts)





if __name__ == "__main__":

    print(build_summary())
