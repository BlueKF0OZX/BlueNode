"""Cached, layered network diagnostics for BlueNode."""

import json
import os
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from event_logger import emit


CONFIG = load_config().get("connectivity", {})
INTERVAL_SECONDS = max(10, int(CONFIG.get("interval_seconds", 30)))
TIMEOUT_SECONDS = max(0.5, float(CONFIG.get("timeout_seconds", 1.5)))
FAILURE_THRESHOLD = max(2, int(CONFIG.get("failure_threshold", 2)))
RECOVERY_THRESHOLD = max(1, int(CONFIG.get("recovery_threshold", 2)))
STALE_SECONDS = max(INTERVAL_SECONDS * 3, int(CONFIG.get("stale_seconds", 120)))
DNS_HOST = str(CONFIG.get("dns_test_host", "example.com"))
EXTERNAL_HOST = str(CONFIG.get("external_test_host", "1.1.1.1"))
EXTERNAL_PORT = int(CONFIG.get("external_test_port", 443))
STATE_FILE = Path("/opt/nodesmart/state/connectivity.json")


def utc_now():
    return datetime.now(timezone.utc)


def _run(command):
    try:
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None


def default_route():
    result = _run(["ip", "-4", "route", "show", "default"])
    if result is None or result.returncode != 0:
        return None, None
    parts = result.stdout.split()
    try:
        return parts[parts.index("dev") + 1], parts[parts.index("via") + 1]
    except (ValueError, IndexError):
        return None, None


def interface_available(interface):
    if not interface:
        return False
    try:
        return (Path("/sys/class/net") / interface / "operstate").read_text().strip() != "down"
    except OSError:
        return None


def gateway_reachable(gateway):
    if not gateway:
        return False
    result = _run(["ping", "-c", "1", "-W", "1", gateway])
    if result is None:
        return None
    if result.returncode == 0:
        return True
    neighbor = _run(["ip", "neigh", "show", gateway])
    if neighbor is None or neighbor.returncode != 0 or not neighbor.stdout.strip():
        return False
    state = neighbor.stdout.upper()
    return not ("FAILED" in state or "INCOMPLETE" in state)


def dns_resolves():
    result = _run(["getent", "ahosts", DNS_HOST])
    return None if result is None else result.returncode == 0 and bool(result.stdout.strip())


def external_reachable():
    try:
        connection = socket.create_connection((EXTERNAL_HOST, EXTERNAL_PORT), TIMEOUT_SECONDS)
        connection.close()
        return True
    except OSError:
        return False


def allstar_registered():
    result = _run(["sudo", "-n", "asterisk", "-rx", "rpt show registrations"])
    if result is None or result.returncode != 0:
        return None
    lines = [line.split() for line in result.stdout.splitlines() if line.split()]
    if any(parts[-1].lower() == "registered" for parts in lines):
        return True
    if "registration" in result.stdout.lower():
        return False
    return None


def run_checks():
    interface, gateway = default_route()
    local = interface_available(interface)
    return {
        "interface": local,
        "interface_name": interface,
        "gateway": gateway_reachable(gateway) if local else False,
        "gateway_address": gateway,
        "dns": dns_resolves() if local else False,
        "internet": external_reachable() if local else False,
        "allstar": allstar_registered(),
    }


def failure_domain(checks):
    if checks.get("interface") is False:
        return "local_network"
    if checks.get("gateway") is False:
        return "gateway"
    if checks.get("internet") is False:
        return "external_internet"
    if checks.get("dns") is False:
        return "dns"
    if checks.get("allstar") is False:
        return "allstar"
    required = ("interface", "gateway", "dns", "internet")
    if any(checks.get(name) is None for name in required):
        return "unavailable"
    return "healthy"


def load_state():
    try:
        with STATE_FILE.open() as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".connectivity-", suffix=".tmp", dir=STATE_FILE.parent)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(state, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, STATE_FILE)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def _message(domain, checks):
    messages = {
        "healthy": "LAN, gateway, DNS, Internet, and AllStar registration are healthy",
        "local_network": "No usable default network interface is available",
        "gateway": "The local interface is available but its default gateway is unreachable",
        "dns": "The gateway and external Internet are reachable, but DNS resolution failed",
        "external_internet": "The LAN and gateway are reachable, but the external Internet probe failed",
        "allstar": "General Internet access is healthy, but AllStar registration is unavailable",
        "unavailable": "Connectivity diagnostics are incomplete or unavailable",
    }
    return messages[domain]


def update(checks=None, now=None):
    now = utc_now() if now is None else now
    checks = run_checks() if checks is None else checks
    previous = load_state()
    domain = failure_domain(checks)
    previous_domain = previous.get("observed_domain")
    try:
        failures = max(0, int(previous.get("consecutive_failures", 0) or 0))
        successes = max(0, int(previous.get("consecutive_successes", 0) or 0))
    except (TypeError, ValueError, OverflowError):
        failures = successes = 0

    if domain == "healthy":
        successes = successes + 1 if previous_domain == "healthy" else 1
        failures = 0
    else:
        failures = failures + 1 if previous_domain == domain else 1
        successes = 0

    sustained = domain not in ("healthy", "unavailable") and failures >= FAILURE_THRESHOLD
    recovering = (domain == "healthy"
                  and (previous.get("sustained") or previous.get("diagnosis") == "recovering")
                  and successes < RECOVERY_THRESHOLD)
    if domain == "healthy" and recovering:
        status, diagnosis = "degraded", "recovering"
    elif domain == "healthy":
        status, diagnosis = "healthy", "healthy"
    elif domain == "unavailable":
        status, diagnosis = "unavailable", "unavailable"
    elif not sustained:
        status, diagnosis = "degraded", "transient"
    elif domain in ("local_network", "gateway", "external_internet"):
        status, diagnosis = "offline", f"{domain}_failure"
    else:
        status, diagnosis = "degraded", f"{domain}_failure"

    state = {
        "status": status, "diagnosis": diagnosis, "failure_domain": domain,
        "observed_domain": domain, "transient": diagnosis == "transient",
        "sustained": sustained, "checks": checks,
        "consecutive_failures": failures, "consecutive_successes": successes,
        "last_check": now.isoformat(), "stale_after_seconds": STALE_SECONDS,
        "message": _message(domain, checks),
        "recovering_from": previous.get("failure_domain") if recovering else None,
    }
    previous_diagnosis = previous.get("diagnosis")
    if previous_diagnosis and previous_diagnosis != diagnosis:
        emit(f"CONNECTIVITY.{diagnosis.upper()}", state["message"])
    save_state(state)
    return state


def public_state(now=None):
    now = utc_now() if now is None else now
    state = load_state()
    try:
        updated = datetime.fromisoformat(state["last_check"])
        stale_after = int(state.get("stale_after_seconds", STALE_SECONDS))
        stale = (now - updated).total_seconds() > stale_after
    except (KeyError, TypeError, ValueError, OverflowError):
        stale = True
    if stale:
        return {"status": "unavailable", "diagnosis": "unavailable",
                "failure_domain": "unavailable", "checks": {}, "stale": True,
                "last_check": state.get("last_check"),
                "message": "Cached connectivity diagnostics are stale"}
    state["stale"] = False
    return state


def legacy_internet_state(state):
    """Preserve the established online/offline field for existing consumers."""
    if state.get("status") == "offline":
        return "offline"
    if state.get("diagnosis") == "transient":
        return "online"
    if state.get("diagnosis") == "recovering":
        return ("offline" if state.get("recovering_from") in
                ("local_network", "gateway", "external_internet") else "online")
    checks = state.get("checks", {})
    if checks.get("internet") is True:
        return "online"
    return "unknown"
