
import json

import subprocess

import socket

from pathlib import Path

from datetime import datetime, timezone

from event_logger import emit
from connection_stats import summarize_connections
from intelligence import build_intelligence
from config import load_config
import radio_activity
import connectivity
import node_behavior






CONFIG = load_config()
NODE = str(CONFIG["node"])
CALLSIGN = str(CONFIG["callsign"])
FRIENDLY_NODES = {str(k): v for k, v in CONFIG.get("friendly_nodes", {}).items()}
HEALTH_CONFIG = CONFIG.get("health", {})

CPU_WARNING = HEALTH_CONFIG.get("cpu_warning_c", 70)
CPU_CRITICAL = HEALTH_CONFIG.get("cpu_critical_c", 80)
MEMORY_WARNING = HEALTH_CONFIG.get("memory_warning_percent", 75)
MEMORY_CRITICAL = HEALTH_CONFIG.get("memory_critical_percent", 90)
DISK_WARNING = HEALTH_CONFIG.get("disk_warning_percent", 80)
DISK_CRITICAL = HEALTH_CONFIG.get("disk_critical_percent", 90)

BASE_DIR = Path("/opt/nodesmart")

STATE_FILE = BASE_DIR / "state" / "system.json"

ALLSTAR_STATE_FILE = BASE_DIR / "events" / "allstar_state.json"





def check_asterisk():

    """Return online if Asterisk responds to its CLI."""

    try:

        result = subprocess.run(

            ["sudo", "-n", "/usr/local/sbin/bluenode-asterisk", "-rx", "core show version"],

            capture_output=True,

            text=True,

            timeout=5,

        )

        return "online" if result.returncode == 0 else "offline"

    except (subprocess.SubprocessError, OSError):

        return "offline"





def check_internet():

    """Check outbound Internet connectivity."""

    try:

        connection = socket.create_connection(("1.1.1.1", 53), timeout=3)

        connection.close()

        return "online"

    except OSError:

        return "offline"





def get_cpu_temp():

    """Return CPU temperature in Celsius."""

    try:

        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()

        return round(int(raw) / 1000, 1)

    except (OSError, ValueError):

        return None





def get_uptime():

    """Return system uptime in seconds."""

    try:

        raw = Path("/proc/uptime").read_text().split()[0]

        return int(float(raw))

    except (OSError, ValueError, IndexError):

        return None





def get_memory_usage():

    """Return RAM usage percentage."""

    try:

        values = {}



        with Path("/proc/meminfo").open() as file:

            for line in file:

                key, value = line.split(":", 1)

                values[key] = int(value.strip().split()[0])



        total = values["MemTotal"]

        available = values["MemAvailable"]

        used = total - available



        return round((used / total) * 100, 1)



    except (OSError, ValueError, KeyError, ZeroDivisionError):

        return None





def get_disk_usage():

    """Return root filesystem usage percentage."""

    try:

        import shutil



        usage = shutil.disk_usage("/")

        return round((usage.used / usage.total) * 100, 1)



    except (OSError, ZeroDivisionError):

        return None





def get_allstar_state():

    """Read connection state maintained by the BlueNode monitor."""

    try:

        with ALLSTAR_STATE_FILE.open("r") as file:

            data = json.load(file)



        return {

            "links": data.get("links", []),

            "connected_since": data.get("connected_since", {})

        }



    except (OSError, json.JSONDecodeError):

        return {

            "links": [],

            "connected_since": {}

        }





def check_skywarn():

    """Read SkywarnPlus Tailmessage enabled/disabled state."""

    config_file = Path("/usr/local/bin/SkywarnPlus/config.yaml")



    try:

        with config_file.open("r") as file:

            lines = file.readlines()



        in_tailmessage = False



        for line in lines:

            stripped = line.strip()



            if stripped == "SKYWARNPLUS:":

                in_tailmessage = True

                continue



            if in_tailmessage:

                if stripped and not line.startswith((" ", "\t")):

                    break



                if stripped.lower().startswith("enable:"):

                    value = stripped.split(":", 1)[1].strip().lower()



                    if value == "true":

                        return "enabled"

                    if value == "false":

                        return "disabled"



        return "unknown"



    except OSError:

        return "unknown"





def evaluate_health(asterisk, internet, cpu_temp, memory_percent, disk_percent,
                    connectivity_state=None):

    """Evaluate BlueNode component health and return overall status."""



    health = {

        "asterisk": "normal",

        "internet": "normal",

        "cpu": "normal",

        "memory": "normal",

        "disk": "normal",

    }



    reasons = []



    if asterisk != "online":

        health["asterisk"] = "critical"

        reasons.append("Asterisk is offline")



    if internet == "offline":

        health["internet"] = "critical"

        reasons.append("Internet connectivity is unavailable")
    elif internet == "unknown":
        health["internet"] = "unknown"
        reasons.append("Internet connectivity diagnostics are unavailable")
    elif connectivity_state and connectivity_state.get("sustained"):
        domain = connectivity_state.get("failure_domain")
        if domain in ("dns", "allstar_services", "allstar_registration", "iax", "remote_link"):
            health["internet"] = "warning"
            reasons.append(connectivity_state.get("message", "Connectivity is degraded"))



    if cpu_temp is None:

        health["cpu"] = "unknown"

        reasons.append("CPU temperature unavailable")

    elif cpu_temp >= CPU_CRITICAL:

        health["cpu"] = "critical"

        reasons.append(f"CPU temperature critical ({cpu_temp:.1f} C)")

    elif cpu_temp >= CPU_WARNING:

        health["cpu"] = "warning"

        reasons.append(f"CPU temperature elevated ({cpu_temp:.1f} C)")



    if memory_percent is None:

        health["memory"] = "unknown"

        reasons.append("Memory usage unavailable")

    elif memory_percent >= MEMORY_CRITICAL:

        health["memory"] = "critical"

        reasons.append(f"Memory usage critical ({memory_percent:.1f}%)")

    elif memory_percent >= MEMORY_WARNING:

        health["memory"] = "warning"

        reasons.append(f"Memory usage elevated ({memory_percent:.1f}%)")



    if disk_percent is None:

        health["disk"] = "unknown"

        reasons.append("Disk usage unavailable")

    elif disk_percent >= DISK_CRITICAL:

        health["disk"] = "critical"

        reasons.append(f"Disk usage critical ({disk_percent:.1f}%)")

    elif disk_percent >= DISK_WARNING:

        health["disk"] = "warning"

        reasons.append(f"Disk usage elevated ({disk_percent:.1f}%)")



    states = health.values()



    if "critical" in states:

        overall = "fault"

    elif "warning" in states or "unknown" in states:

        overall = "degraded"

    else:

        overall = "healthy"



    return overall, health, reasons





def build_state():

    asterisk = check_asterisk()

    connectivity_state = connectivity.public_state()
    internet = connectivity.legacy_internet_state(connectivity_state)

    allstar_state = get_allstar_state()
    connected_nodes = allstar_state["links"]
    connected_since = allstar_state["connected_since"]

    skywarn = check_skywarn()

    cpu_temp = get_cpu_temp()

    uptime_seconds = get_uptime()

    memory_percent = get_memory_usage()

    disk_percent = get_disk_usage()

    connection_stats = summarize_connections()



    status, health, health_reasons = evaluate_health(

        asterisk,

        internet,

        cpu_temp,

        memory_percent,

        disk_percent,
        connectivity_state,

    )



    state = {

        "node": NODE,

        "callsign": CALLSIGN,
        "friendly_nodes": FRIENDLY_NODES,

        "status": status,

        "health": health,

        "health_reasons": health_reasons,

        "asterisk": asterisk,

        "internet": internet,
        "connectivity": connectivity_state,

        "skywarn": skywarn,

        "cpu_temp_c": cpu_temp,

        "uptime_seconds": uptime_seconds,

        "memory_percent": memory_percent,

        "disk_percent": disk_percent,

        "connected_nodes": connected_nodes,
        "connected_since": connected_since,
        "connection_stats": connection_stats,
        "radio_activity": radio_activity.public_state(),
        "node_behavior": node_behavior.public_state(),

        "nodesmart": "running",

        "last_health_check": datetime.now(timezone.utc).isoformat(),

    }

    return state







def load_previous_state():

    """Read the previous BlueNode state for transition detection."""



    try:

        with STATE_FILE.open("r") as file:

            return json.load(file)



    except (OSError, json.JSONDecodeError):

        return None





def log_state_changes(previous, current):

    """Emit events only when meaningful BlueNode state changes occur."""



    if not previous:

        return



    old_status = previous.get("status")

    new_status = current.get("status")



    if old_status != new_status:

        reasons = current.get("health_reasons", [])



        message = f"{old_status} -> {new_status}"



        if reasons:

            message += " | " + "; ".join(reasons)



        emit(f"SYSTEM.{new_status.upper()}", message)



    old_health = previous.get("health", {})

    new_health = current.get("health", {})



    component_values = {

        "cpu": ("cpu_temp_c", " C"),

        "memory": ("memory_percent", "%"),

        "disk": ("disk_percent", "%"),

    }



    for component in ("asterisk", "internet", "cpu", "memory", "disk"):

        old_state = old_health.get(component)

        new_state = new_health.get(component)



        if old_state == new_state:

            continue



        message = f"{old_state} -> {new_state}"



        if component in component_values:

            value_key, suffix = component_values[component]

            value = current.get(value_key)



            if value is not None:

                message += f" ({value}{suffix})"



        emit(

            f"HEALTH.{component.upper()}.{str(new_state).upper()}",

            message

        )



    for component in ("asterisk", "internet"):

        old_value = previous.get(component)

        new_value = current.get(component)



        if old_value != new_value:

            emit(

                f"{component.upper()}.{str(new_value).upper()}",

                f"{old_value} -> {new_value}"

            )



    old_skywarn = previous.get("skywarn")

    new_skywarn = current.get("skywarn")



    if old_skywarn != new_skywarn:

        emit(

            f"SKYWARN.{str(new_skywarn).upper()}",

            f"{old_skywarn} -> {new_skywarn}"

        )





def save_state(state):

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)



    temp_file = STATE_FILE.with_suffix(".tmp")



    with temp_file.open("w") as file:

        json.dump(state, file, indent=2)



    temp_file.replace(STATE_FILE)





if __name__ == "__main__":



    previous_state = load_previous_state()



    state = build_state()



    log_state_changes(previous_state, state)



    state["intelligence"] = build_intelligence(state)
    state["intelligence_summary"] = state["intelligence"]["summary"]

    save_state(state)



    print(json.dumps(state, indent=2))
