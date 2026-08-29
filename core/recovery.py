#!/usr/bin/env python3



import json

import subprocess

import time

from datetime import datetime, timezone

from pathlib import Path



from event_logger import emit

from config import load_config





CONFIG = load_config()

RECOVERY_CONFIG = CONFIG.get("recovery", {})



ASTERISK_RECOVERY_ENABLED = RECOVERY_CONFIG.get(

    "asterisk_enabled",

    True,

)



COOLDOWN_SECONDS = int(

    RECOVERY_CONFIG.get(

        "asterisk_cooldown_seconds",

        600,

    )

)



MAX_ATTEMPTS = int(

    RECOVERY_CONFIG.get(

        "asterisk_max_attempts",

        3,

    )

)



ATTEMPT_WINDOW_SECONDS = int(

    RECOVERY_CONFIG.get(

        "asterisk_attempt_window_seconds",

        3600,

    )

)



LOCKOUT_SECONDS = int(

    RECOVERY_CONFIG.get(

        "asterisk_lockout_seconds",

        3600,

    )

)



STATE_FILE = Path("/opt/nodesmart/state/system.json")

RECOVERY_STATE_FILE = Path("/opt/nodesmart/state/recovery.json")





def asterisk_online():

    try:

        result = subprocess.run(

            [

                "sudo",

                "-n",

                "asterisk",

                "-rx",

                "core show version",

            ],

            capture_output=True,

            text=True,

            timeout=5,

        )



        return result.returncode == 0



    except (subprocess.SubprocessError, OSError):

        return False





def load_system_state():

    try:

        with STATE_FILE.open() as file:

            return json.load(file)



    except (OSError, json.JSONDecodeError):

        return None





def load_recovery_state():

    try:

        with RECOVERY_STATE_FILE.open() as file:

            return json.load(file)



    except (OSError, json.JSONDecodeError):

        return {}





def save_recovery_state(data):

    RECOVERY_STATE_FILE.parent.mkdir(

        parents=True,

        exist_ok=True,

    )



    temp_file = RECOVERY_STATE_FILE.with_suffix(".tmp")



    with temp_file.open("w") as file:

        json.dump(data, file, indent=2)



    temp_file.replace(RECOVERY_STATE_FILE)





def record_recovery_result(status, message):

    recovery_state = load_recovery_state()



    recovery_state["last_recovery"] = {

        "component": "asterisk",

        "status": status,

        "message": message,

        "timestamp": datetime.now(

            timezone.utc

        ).isoformat(),

    }



    save_recovery_state(recovery_state)





def clear_recovery_limits():

    recovery_state = load_recovery_state()



    recovery_state["asterisk_attempt_history"] = []

    recovery_state["asterisk_lockout_until"] = 0



    save_recovery_state(recovery_state)





def recover_asterisk():

    if not ASTERISK_RECOVERY_ENABLED:

        return



    state = load_system_state()



    if not state:

        return



    if state.get("asterisk") != "offline":

        return



    # Health already detected a failure.

    # Wait and independently confirm before acting.

    time.sleep(5)



    if asterisk_online():

        emit(

            "RECOVERY.ASTERISK.CANCELLED",

            (

                "Asterisk responded during verification; "

                "restart not required"

            ),

        )



        record_recovery_result(

            "cancelled",

            (

                "Asterisk responded during verification; "

                "restart not required"

            ),

        )



        return



    recovery_state = load_recovery_state()

    now = int(time.time())



    # --------------------------------------------------------

    # Circuit-breaker lockout

    # --------------------------------------------------------



    lockout_until = int(

        recovery_state.get(

            "asterisk_lockout_until",

            0,

        )

        or 0

    )



    if lockout_until > now:

        return



    if lockout_until:

        recovery_state["asterisk_lockout_until"] = 0



    # --------------------------------------------------------

    # Standard cooldown

    # --------------------------------------------------------



    last_attempt = int(

        recovery_state.get(

            "asterisk_last_attempt",

            0,

        )

        or 0

    )



    if now - last_attempt < COOLDOWN_SECONDS:

        save_recovery_state(recovery_state)

        return



    # --------------------------------------------------------

    # Attempt-rate protection

    # --------------------------------------------------------



    history = recovery_state.get(

        "asterisk_attempt_history",

        [],

    )



    history = [

        int(timestamp)

        for timestamp in history

        if now - int(timestamp)

        < ATTEMPT_WINDOW_SECONDS

    ]



    if len(history) >= MAX_ATTEMPTS:

        lockout_until = now + LOCKOUT_SECONDS



        recovery_state[

            "asterisk_attempt_history"

        ] = history



        recovery_state[

            "asterisk_lockout_until"

        ] = lockout_until



        save_recovery_state(recovery_state)



        message = (

            f"Automatic recovery locked out after "

            f"{len(history)} attempts within "

            f"{ATTEMPT_WINDOW_SECONDS // 60} minutes"

        )



        emit(

            "RECOVERY.ASTERISK.LOCKOUT",

            message,

        )



        record_recovery_result(

            "lockout",

            message,

        )



        return



    history.append(now)



    recovery_state[

        "asterisk_attempt_history"

    ] = history



    recovery_state[

        "asterisk_last_attempt"

    ] = now



    save_recovery_state(recovery_state)



    emit(

        "RECOVERY.ASTERISK.ATTEMPT",

        (

            "Confirmed Asterisk offline; "

            "attempting service restart"

        ),

    )



    try:

        result = subprocess.run(

            [

                "sudo",

                "-n",

                "systemctl",

                "restart",

                "asterisk",

            ],

            capture_output=True,

            text=True,

            timeout=20,

        )



    except subprocess.TimeoutExpired:

        emit(

            "RECOVERY.ASTERISK.FAILED",

            "Asterisk restart command timed out",

        )



        record_recovery_result(

            "failed",

            "Asterisk restart command timed out",

        )



        return



    except OSError as exc:

        message = (

            f"Unable to execute restart: {exc}"

        )



        emit(

            "RECOVERY.ASTERISK.FAILED",

            message,

        )



        record_recovery_result(

            "failed",

            message,

        )



        return



    if result.returncode != 0:

        message = (

            result.stderr.strip()

            or result.stdout.strip()

            or (

                "systemctl exited with status "

                f"{result.returncode}"

            )

        )



        emit(

            "RECOVERY.ASTERISK.FAILED",

            message,

        )



        record_recovery_result(

            "failed",

            message,

        )



        return



    # Give Asterisk time to finish starting before

    # independently verifying the result.

    time.sleep(8)



    if asterisk_online():

        emit(

            "RECOVERY.ASTERISK.SUCCESS",

            (

                "Asterisk restarted and passed "

                "verification"

            ),

        )



        record_recovery_result(

            "success",

            (

                "Asterisk restarted and passed "

                "verification"

            ),

        )



        # A successful recovery resets the circuit breaker.

        clear_recovery_limits()



    else:

        emit(

            "RECOVERY.ASTERISK.FAILED",

            (

                "Restart completed but Asterisk "

                "still did not respond"

            ),

        )



        record_recovery_result(

            "failed",

            (

                "Restart completed but Asterisk "

                "still did not respond"

            ),

        )





if __name__ == "__main__":

    recover_asterisk()
