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


ROOT_CONFIG = load_config()
CONFIG = ROOT_CONFIG.get("connectivity", {})
NODE = str(ROOT_CONFIG["node"])
INTERVAL_SECONDS = max(10, int(CONFIG.get("interval_seconds", 30)))
TIMEOUT_SECONDS = max(0.5, float(CONFIG.get("timeout_seconds", 1.5)))
FAILURE_THRESHOLD = max(2, int(CONFIG.get("failure_threshold", 2)))
RECOVERY_THRESHOLD = max(1, int(CONFIG.get("recovery_threshold", 2)))
STALE_SECONDS = max(INTERVAL_SECONDS * 3, int(CONFIG.get("stale_seconds", 120)))
DNS_HOST = str(CONFIG.get("dns_test_host", "example.com"))
EXTERNAL_HOST = str(CONFIG.get("external_test_host", "1.1.1.1"))
EXTERNAL_PORT = int(CONFIG.get("external_test_port", 443))
ALLSTAR_HOST = str(CONFIG.get("allstar_service_host", "register.allstarlink.org"))
ALLSTAR_PORT = int(CONFIG.get("allstar_service_port", 443))
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


def tcp_reachable(host, port):
    try:
        connection = socket.create_connection((host, port), TIMEOUT_SECONDS)
        connection.close()
        return True
    except OSError:
        return False


def asterisk_available():
    result = _run(["sudo", "-n", "asterisk", "-rx", "core show uptime seconds"])
    return None if result is None else result.returncode == 0 and "uptime" in result.stdout.lower()


def iax_available():
    result = _run(["sudo", "-n", "asterisk", "-rx", "module show like chan_iax2"])
    if result is None or result.returncode != 0:
        return None
    output = result.stdout.lower()
    if "chan_iax2.so" not in output:
        return False
    return "running" in output


def remote_link_states():
    result = _run(["sudo", "-n", "asterisk", "-rx", f"rpt lstats {NODE}"])
    if result is None or result.returncode != 0:
        return None
    links = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        state = parts[-1].lower()
        if state not in ("established", "connecting"):
            continue
        links.append({"node": parts[0], "state": state,
                      "direction": parts[-3].lower(),
                      "evidence": f"App_Rpt reports {state}"})
    return links


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
    gateway_ok = gateway_reachable(gateway) if local else None
    dns = dns_resolves() if gateway_ok else None
    internet = external_reachable() if gateway_ok else None
    allstar_service = (tcp_reachable(ALLSTAR_HOST, ALLSTAR_PORT)
                       if dns is True and internet is True else None)
    asterisk = asterisk_available()
    registration = allstar_registered() if asterisk is True else None
    iax = iax_available() if asterisk is True else None
    remote_links = remote_link_states() if asterisk is True and iax is True else None
    return {
        "interface": local,
        "interface_name": interface,
        "gateway": gateway_ok,
        "gateway_address": gateway,
        "dns": dns,
        "internet": internet,
        "allstar_services": allstar_service,
        "allstar": registration,
        "asterisk": asterisk,
        "iax": iax,
        "remote_links": remote_links,
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
    if checks.get("allstar_services") is False:
        return "allstar_services"
    if checks.get("asterisk") is False:
        return "asterisk"
    if checks.get("allstar") is False:
        return "allstar_registration"
    if checks.get("iax") is False:
        return "iax"
    remote_links = checks.get("remote_links")
    if isinstance(remote_links, list) and any(
            link.get("state") in ("connecting", "failed", "terminated", "unreachable")
            for link in remote_links if isinstance(link, dict)):
        return "remote_link"
    required = ("interface", "gateway", "dns", "internet")
    if any(checks.get(name) is None for name in required):
        return "unavailable"
    optional = ("allstar_services", "allstar", "asterisk", "iax")
    if any(name in checks and checks.get(name) is None for name in optional):
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


def _layer(status, evidence):
    return {"status": status, "evidence": evidence}


def diagnostic_layers(checks):
    """Build a truthful chain, marking untested downstream layers as blocked."""
    layers = {}
    local = checks.get("interface")
    layers["local_network"] = _layer(
        "ok" if local is True else "fail" if local is False else "unknown",
        (f"Default-route interface {checks.get('interface_name')} is available"
         if local is True else "No usable default-route interface was observed"
         if local is False else "Interface state could not be read"))

    gateway = checks.get("gateway")
    if local is not True:
        layers["gateway"] = _layer("blocked_by_upstream", "Requires a usable local interface")
    else:
        layers["gateway"] = _layer(
            "ok" if gateway is True else "fail" if gateway is False else "unknown",
            "Default gateway is reachable" if gateway is True else
            "Default gateway did not answer ping or neighbor checks" if gateway is False else
            "Gateway reachability could not be determined")

    upstream_gateway = local is True and gateway is True
    for key, label in (("dns", "DNS resolution"), ("internet", "Direct-IP Internet probe")):
        value = checks.get(key)
        if not upstream_gateway:
            layers[key] = _layer("blocked_by_upstream", "Requires a reachable default gateway")
        else:
            layers[key] = _layer(
                "ok" if value is True else "fail" if value is False else "unknown",
                f"{label} succeeded" if value is True else
                f"{label} failed" if value is False else f"{label} was unavailable")

    services = checks.get("allstar_services")
    if not upstream_gateway or checks.get("internet") is not True:
        layers["allstar_services"] = _layer(
            "blocked_by_upstream", "Requires working gateway and Internet connectivity")
    elif checks.get("dns") is not True:
        layers["allstar_services"] = _layer(
            "blocked_by_upstream", "AllStar hostname access is blocked by DNS")
    else:
        layers["allstar_services"] = _layer(
            "ok" if services is True else "fail" if services is False else "unknown",
            f"{ALLSTAR_HOST}:{ALLSTAR_PORT} is reachable" if services is True else
            "The configured AllStar service endpoint is unreachable" if services is False else
            "AllStar service reachability was unavailable")

    asterisk = checks.get("asterisk")
    layers["asterisk"] = _layer(
        "ok" if asterisk is True else "fail" if asterisk is False else "unknown",
        "Asterisk CLI is responsive" if asterisk is True else
        "Asterisk CLI is unavailable" if asterisk is False else
        "Asterisk availability was not determined")

    service_ok = layers["allstar_services"]["status"] == "ok"
    registration = checks.get("allstar")
    if asterisk is not True:
        layers["allstar_registration"] = _layer(
            "blocked_by_upstream", "Registration state requires responsive Asterisk")
    elif registration is True:
        layers["allstar_registration"] = _layer("ok", "App_Rpt reports registered")
    elif not service_ok:
        layers["allstar_registration"] = _layer(
            "blocked_by_upstream", "Current registration health depends on AllStar service access")
    else:
        layers["allstar_registration"] = _layer(
            "ok" if registration is True else "fail" if registration is False else "unknown",
            "App_Rpt reports registered" if registration is True else
            "App_Rpt does not report a registered node" if registration is False else
            "Registration state was unavailable")

    iax = checks.get("iax")
    if asterisk is not True:
        layers["iax"] = _layer("blocked_by_upstream", "IAX requires responsive Asterisk")
    else:
        layers["iax"] = _layer(
            "ok" if iax is True else "fail" if iax is False else "unknown",
            "Asterisk chan_iax2 is loaded and running" if iax is True else
            "Asterisk chan_iax2 is not running" if iax is False else
            "IAX module state was unavailable")

    links = checks.get("remote_links")
    if iax is not True:
        layers["remote_links"] = _layer("blocked_by_upstream", "Remote links require IAX")
    elif links is None:
        layers["remote_links"] = _layer("unknown", "Remote link state was unavailable")
    else:
        troubled = [link for link in links if isinstance(link, dict)
                    and link.get("state") != "established"]
        layers["remote_links"] = _layer(
            "fail" if troubled else "ok",
            ("App_Rpt reports non-established link state for " +
             ", ".join(str(link.get("node", "unknown")) for link in troubled))
            if troubled else
            (f"App_Rpt reports {len(links)} established remote link(s)" if links
             else "App_Rpt reports no current remote link records"))
        layers["remote_links"]["links"] = links
    return layers


def _message(domain, checks):
    messages = {
        "healthy": "LAN, gateway, DNS, Internet, AllStar, Asterisk, and IAX checks are healthy",
        "local_network": "No usable default network interface is available",
        "gateway": "The local interface is available but its default gateway is unreachable",
        "dns": "The gateway and external Internet are reachable, but DNS resolution failed",
        "external_internet": "The LAN and gateway are reachable, but the external Internet probe failed",
        "allstar_services": "General Internet access works, but the AllStar service endpoint is unreachable",
        "allstar_registration": "AllStar services and Asterisk are available, but App_Rpt is not registered",
        "asterisk": "Network connectivity works, but the local Asterisk service is unavailable",
        "iax": "Asterisk is available, but its IAX link layer is not running",
        "remote_link": "Core services are healthy, but App_Rpt reports a remote link is not established",
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
        "layers": diagnostic_layers(checks),
        "recovering_from": previous.get("failure_domain") if recovering else None,
    }
    if domain == "healthy":
        state["operator_action"] = "No operator action required"
    elif diagnosis == "transient":
        state["operator_action"] = "BlueNode is waiting for confirmation before escalating"
    elif domain in ("local_network", "gateway"):
        state["operator_action"] = "Check the local interface, cable/Wi-Fi, and router"
    elif domain == "dns":
        state["operator_action"] = "Check the configured DNS resolver; direct-IP Internet remains available"
    elif domain == "external_internet":
        state["operator_action"] = "Check the upstream Internet connection or ISP"
    elif domain in ("allstar_services", "allstar_registration"):
        state["operator_action"] = "Check AllStar service status and node registration"
    elif domain in ("asterisk", "iax"):
        state["operator_action"] = "Inspect the local Asterisk service and IAX module"
    elif domain == "remote_link":
        state["operator_action"] = "Inspect the named link; BlueNode cannot infer the remote cause"
    else:
        state["operator_action"] = "Wait for fresh diagnostics or inspect unavailable probes"
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
                "message": "Cached connectivity diagnostics are stale",
                "operator_action": "Wait for the next diagnostic refresh",
                "layers": {}}
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
