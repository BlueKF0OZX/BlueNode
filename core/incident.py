
#!/usr/bin/env python3



from datetime import datetime, timezone

from intelligence import load_events





def build_asterisk_incidents(events=None):

    """

    Group Asterisk failure/recovery events into incidents.



    An incident begins with ASTERISK.OFFLINE and ends when

    ASTERISK.ONLINE is observed.



    Recovery attempts and their outcomes are associated with

    the active incident.

    """



    if events is None:

        events = load_events()



    incidents = []

    current = None



    for event in events:

        event_type = event.get("event")

        event_time = event.get("timestamp")



        if not isinstance(event_time, datetime):

            continue



        if event_time.tzinfo is None:

            event_time = event_time.replace(tzinfo=timezone.utc)



        event_time = event_time.astimezone(timezone.utc)



        if event_type == "ASTERISK.OFFLINE":

            # If another offline event occurs before the previous

            # incident resolves, keep it as the same incident.

            if current is None:

                current = {

                    "component": "asterisk",

                    "started_at": event_time.isoformat(),

                    "ended_at": None,

                    "duration_seconds": None,

                    "recovery_attempted": False,

                    "recovery_status": None,

                    "resolved": False,

                }



        elif current is not None:



            if event_type == "RECOVERY.ASTERISK.ATTEMPT":

                current["recovery_attempted"] = True



            elif event_type == "RECOVERY.ASTERISK.SUCCESS":

                current["recovery_status"] = "success"



            elif event_type == "RECOVERY.ASTERISK.FAILED":

                current["recovery_status"] = "failed"



            elif event_type == "RECOVERY.ASTERISK.CANCELLED":

                current["recovery_status"] = "cancelled"



            elif event_type == "ASTERISK.ONLINE":

                current["ended_at"] = event_time.isoformat()



                started = datetime.fromisoformat(

                    current["started_at"]

                )



                current["duration_seconds"] = max(

                    0,

                    int((event_time - started).total_seconds())

                )



                current["resolved"] = True



                incidents.append(current)

                current = None



    # Preserve an unresolved incident if Asterisk has not

    # returned online yet.

    if current is not None:

        incidents.append(current)



    return incidents





def recent_asterisk_incidents(hours=24):

    """Return Asterisk incidents from the requested time window."""



    now = datetime.now(timezone.utc)



    cutoff = now.timestamp() - (hours * 3600)



    incidents = build_asterisk_incidents()



    recent = []



    for incident in incidents:

        try:

            started = datetime.fromisoformat(

                incident["started_at"]

            )



            if started.timestamp() >= cutoff:

                recent.append(incident)



        except (KeyError, TypeError, ValueError):

            continue



    return recent





def latest_asterisk_incident():

    """Return the most recent Asterisk incident, if one exists."""



    incidents = build_asterisk_incidents()



    if not incidents:

        return None



    return incidents[-1]





if __name__ == "__main__":

    import json



    print(

        json.dumps(

            build_asterisk_incidents(),

            indent=2

        )

    )
